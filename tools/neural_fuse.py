#!/usr/bin/env python3
"""HOST-ONLY reference model of one in-weight superinstruction: LIJ ("load immediate, jump over").

NOT part of the shipped model. The Qwen3.5 checkpoint contains no LIJ uop, so none of this runs
inside the neural computer; it is the executable specification a circuit change would have to
match, plus the host-side ROM peephole that would feed it. See docs/research/NEURAL_EXECUTOR.md
section 3 for the circuit design and its costs.

Fusion (the smallest one that needs no second ROM read and no second register write):

    lui   rd, hi20          LIJ rd, imm20          (rd != x0)
    addi  rd, rd, lo12  =>  one 1-token record J(w + 2)

  * only when the pair is a constant load whose 32-bit result c fits a signed 20-bit field
    (every DROM / ROM / RAM address: 0x20000..0x7ffff < 2^19), so the value rides in the ROM
    word's 20 free bits (the same RS1/RS2/S0..S9 bits LUI uses for its upper 20);
  * the same for auipc+addi (the host knows the pc, so c = pc + imm + lo12 is a constant);
  * rd1 == rd2, so the first result is provably dead and only ONE register write is needed;
  * the ROM word at w is replaced; the word at w + 1 stays the original addi, so a branch that
    targets the addi still runs it alone (identical to the sequential machine);
  * the record is a single J token whose payload is w + 2 (new anchor, n = 0), and rd's value
    is written from circuit dims at t-1 exactly like a JAL's link (core.py jl[], lag-1 Chan),
    not from payload tokens. Token cost 1 instead of 4 for a typical 0x2xxxx address (lui: V F1,
    addi: V F1), instructions retired 2.

``FusedMachine`` subclasses the official ``chipformer.rv.ref.Machine`` and is checked against the
unmodified machine by ``check_equivalence`` (tests/test_neural_fuse.py: randomized programs,
state compared after every fused record).
"""
import argparse
import random
import sys

M32 = 0xFFFFFFFF
OPC_LIJ = 0x5B  # custom-2: U-type, imm20 sign-extended (the fused word as it sits in m.rom)
UOP_LIJ = 70    # the uop id a circuit would give it (custom range 64..127 is free from 70 on)


def sx(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


# ---- tiny RV32 encoders (for the randomized tests) ---------------------------------------------
def enc_u(op, rd, imm20): return (imm20 & 0xFFFFF) << 12 | rd << 7 | op
def enc_i(op, rd, f3, rs1, imm): return (imm & 0xFFF) << 20 | rs1 << 15 | f3 << 12 | rd << 7 | op
def enc_r(rd, f3, rs1, rs2, f7): return f7 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | rd << 7 | 0x33
def enc_s(f3, rs1, rs2, imm):
    return (imm >> 5 & 0x7F) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | (imm & 31) << 7 | 0x23
def enc_b(f3, rs1, rs2, off):
    return ((off >> 12 & 1) << 31 | (off >> 5 & 63) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12
            | (off >> 1 & 15) << 8 | (off >> 11 & 1) << 7 | 0x63)


def lui(rd, hi20): return enc_u(0x37, rd, hi20)
def auipc(rd, hi20): return enc_u(0x17, rd, hi20)
def addi(rd, rs, imm): return enc_i(0x13, rd, 0, rs, imm)


def lij_word(rd, imm20):
    """The raw fused word placed into ROM position w."""
    return enc_u(OPC_LIJ, rd, imm20 & 0xFFFFF)


def lij_rom_word(rd, imm20):
    """What the circuit's pre-decoded ROM word for LIJ would hold (core.py / ref.rom_word layout):
    b0 = uop | S0<<7, b1 = RD<<3 | S1..S3, b2 = RS1<<3 | S4..S6, b3 = RS2<<3 | S7..S9, with the
    20-bit value in RS1 (bits 0..4), RS2 (5..9) and S0..S9 (10..19) like LUI's upper field."""
    u = imm20 & 0xFFFFF
    rs1, rs2, spare = u & 31, u >> 5 & 31, u >> 10
    b0 = UOP_LIJ | (spare & 1) << 7
    b1 = rd << 3 | (spare >> 1 & 7)
    b2 = rs1 << 3 | (spare >> 4 & 7)
    b3 = rs2 << 3 | (spare >> 7 & 7)
    return b0 | b1 << 8 | b2 << 16 | b3 << 24


def lij_fields(word):
    """Inverse of lij_rom_word: (rd, signed imm20), to prove the layout loses nothing."""
    b0, b1, b2, b3 = word & 255, word >> 8 & 255, word >> 16 & 255, word >> 24
    assert b0 & 127 == UOP_LIJ
    spare = (b0 >> 7) | (b1 & 7) << 1 | (b2 & 7) << 4 | (b3 & 7) << 7
    u = (b2 >> 3) | (b3 >> 3) << 5 | spare << 10
    return b1 >> 3, sx(u, 20)


# ---- the host peephole -------------------------------------------------------------------------
def fuse_rom(rom, rom_base, decode, n_words=None):
    """Return (new_rom, fused_positions). ``rom`` is the list of raw words from ROM_BASE."""
    out = list(rom)
    n = len(rom) if n_words is None else n_words
    fused = []
    for w in range(n - 2):
        a, b = rom[w], rom[w + 1]
        if not a or not b:
            continue
        ia, ib = decode(a), decode(b)
        if ia.op not in ("LUI", "AUIPC") or ib.op != "ADDI":
            continue
        if not ia.rd or ib.rd != ia.rd or ib.rs1 != ia.rd:
            continue
        pc = rom_base + 4 * w
        c = ((ia.imm if ia.op == "LUI" else pc + ia.imm) + ib.imm) & M32
        s = sx(c, 32)
        if not -(1 << 19) <= s < 1 << 19:
            continue
        out[w] = lij_word(ia.rd, s)
        fused.append(w)
    return out, fused


def make_fused_machine_class():
    from chipformer.rv import ref, spec as S

    class FusedMachine(ref.Machine):
        """ref.Machine plus the LIJ record."""

        def record(self):
            if self.n == S.N_MAX:  # the R refresh comes first, exactly as for any instruction
                return super().record()
            w = self.anchor + self.n
            word = self.rom[w]
            if word & 0x7F != OPC_LIJ:
                return super().record()
            ins_rd, imm = word >> 7 & 31, sx(word >> 12, 20)
            self.steps += 2  # two guest instructions retire in this record
            if ins_rd:
                self.x[ins_rd] = imm & M32
            self.anchor, self.n = w + 2, 0
            return [S.tok("J", self.anchor)]

    return FusedMachine


def _fresh(ref, S, words, ramwords=None):
    rom = list(words) + [0] * (S.ROM_WORDS - len(words))
    ram = list(ramwords) if ramwords else [0] * S.RAM_WORDS
    x = [0] * 32
    x[2] = S.SP_INIT
    return rom, ram, x


def random_program(rng, n=60):
    """Random straight-line-ish RV32IM code with fusable pairs, forward branches, safe memory."""
    rr = [5, 6, 7, 10, 11, 12, 13, 14, 15]
    words, i = [], 0
    while len(words) < n:
        k = rng.random()
        rd, rs1, rs2 = rng.choice(rr), rng.choice(rr), rng.choice(rr)
        if k < 0.22:  # fusable li / la pair (hi chosen around the signed-20 boundary)
            hi = rng.randint(-140, 140) & 0xFFFFF
            words += [lui(rd, hi), addi(rd, rd, rng.randint(-2048, 2047))]
        elif k < 0.30:
            words += [auipc(rd, rng.randint(-3, 130) & 0xFFFFF), addi(rd, rd, rng.randint(-2048, 2047))]
        elif k < 0.36:  # NOT fusable: rd differs / second reads another reg
            words += [lui(rd, rng.randint(0, 0xFFFFF)), addi(rng.choice(rr), rs1, rng.randint(-5, 5))]
        elif k < 0.55:
            words.append(addi(rd, rs1, rng.randint(-2048, 2047)))
        elif k < 0.75:
            f3, f7 = rng.choice([(0, 0), (0, 0x20), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (5, 0x20),
                                 (6, 0), (7, 0), (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1),
                                 (6, 1), (7, 1)])
            words.append(enc_r(rd, f3, rs1, rs2, f7))
        elif k < 0.83:
            words.append(enc_i(0x03, rd, 2, 0, rng.randrange(0, 2040, 4)))        # lw rd, imm(x0)
        elif k < 0.90:
            words.append(enc_s(2, 0, rs2, rng.randrange(0, 2040, 4)))             # sw rs2, imm(x0)
        else:  # forward branch, possibly into the middle of a fusable pair
            off = 4 * rng.randint(2, 4)
            words.append(enc_b(rng.choice([0, 1, 4, 5, 6, 7]), rs1, rs2, off))
    words += [addi(17, 0, 93), 0x73]
    # forward branches may overshoot the tail: pad with exits
    words += [addi(17, 0, 93), 0x73] * 3
    return words


def check_equivalence(words, max_records=2000, ramwords=None):
    """Run the plain machine and the fused one side by side. After every fused record the plain
    machine is advanced by exactly the instructions that record retired and the committed state
    (registers, RAM, pc, console, halted) must be identical. Returns stats."""
    from chipformer.rv import elf as _e, ref, spec as S  # noqa: F401
    FM = make_fused_machine_class()
    rom0, ram0, x0 = _fresh(ref, S, words, ramwords)
    rom1, fused = fuse_rom(rom0, S.ROM_BASE, ref.decode, len(words))
    plain = ref.Machine(list(rom0), list(ram0), list(x0), 0)
    fm = FM(list(rom1), list(ram0), list(x0), 0)
    st = dict(fused_records=0, tokens_plain=0, tokens_fused=0, instr=0, fusable_positions=len(fused))
    for _ in range(max_records):
        if plain.halted or fm.halted:
            break
        s_before = fm.steps
        tf = fm.record()
        retired = fm.steps - s_before
        if tf and retired == 2:
            st['fused_records'] += 1
        # the plain machine must retire the same number of instructions (R refresh = 0)
        tp_all = []
        target = plain.steps + retired
        while plain.steps < target and not plain.halted:
            tp_all += plain.record()
        assert plain.steps == fm.steps, (plain.steps, fm.steps)
        assert plain.x == fm.x, 'registers diverged'
        assert plain.ram == fm.ram, 'RAM diverged'
        assert plain.pc == fm.pc, 'pc diverged'
        assert bytes(plain.out) == bytes(fm.out)
        assert plain.halted == fm.halted
        st['tokens_plain'] += len(tp_all)
        st['tokens_fused'] += len(tf)
        st['instr'] += retired
    return st


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--trials', type=int, default=300)
    ap.add_argument('--seed', type=int, default=1)
    args = ap.parse_args()
    try:
        import chipformer.rv.ref  # noqa: F401
    except ImportError:
        sys.exit('needs the upstream reference: PYTHONPATH=<qwenputer>/experimental/riscv')
    rng = random.Random(args.seed)
    tot = dict(fused_records=0, tokens_plain=0, tokens_fused=0, instr=0, fusable_positions=0)
    for t in range(args.trials):
        st = check_equivalence(random_program(rng))
        for k in tot:
            tot[k] += st[k]
    print(f'{args.trials} random programs: fused state == sequential state after every fused record')
    print(tot)
    print(f"tokens {tot['tokens_plain']} -> {tot['tokens_fused']} "
          f"({100 * (1 - tot['tokens_fused'] / tot['tokens_plain']):.1f}% fewer) on these synthetic programs "
          '(synthetic mix, NOT the DOOM trace; see neural_trace_profile.py for real frequencies)')


if __name__ == '__main__':
    main()
