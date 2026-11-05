#!/usr/bin/env python3
"""HOST-ONLY (no GPU, no model): where do the chip tokens of a QwenOS guest trace go?

Runs the official Qwenputer reference machine (chipformer.rv.ref.Machine, the same token source
the lockstep oracle uses) on a guest ELF for a window of instructions and tallies, per
instruction class and per consecutive instruction pair, how many chip tokens the trace spends.
This is arithmetic over the reference trace; it is NOT a measurement of the neural model.

  PYTHONPATH=<qwenputer>/experimental/riscv python3 -I tools/neural_trace_profile.py \
      --elf build/demo/qwenos-e1m1.elf --kernel-elf build/kernel-doomd.elf --disk E1.img \
      --skip 3420000 --count 1000000 --json out.json

--skip instructions are executed but not tallied (use it to jump past boot / level load; the
reference runs at roughly 100k instr/s, so 4.4M instructions take about a minute).
Liveness is conservative: the first result of a pair counts as dead only when the second
instruction overwrites the same register (rd1 == rd2), so reported savings are lower bounds
for "dead intermediate" fusions.
"""
import argparse
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from upstream_ref import symbols, ReferenceDiskDevice  # noqa: E402

CONTROL = {'BEQ', 'BNE', 'BLT', 'BGE', 'BLTU', 'BGEU', 'JAL', 'JALR', 'ECALL', 'EBREAK'}
STORES = {'SB', 'SH', 'SW'}


def pair_kind(a, b):
    """Name the fusion candidate a pair (a then b, both decoded Inst) belongs to, or None."""
    if a.op in CONTROL or a.op in STORES or not a.rd:
        return None
    dead = b.rd == a.rd  # b overwrites a's result: a's result is provably dead
    uses = a.rd in (b.rs1, b.rs2) if b.op not in ('LUI', 'AUIPC') else False
    if a.op == 'LUI' and b.op == 'ADDI' and dead and b.rs1 == a.rd:
        return 'li32 (lui+addi, same rd)'
    if a.op == 'AUIPC' and b.op == 'ADDI' and dead and b.rs1 == a.rd:
        return 'la (auipc+addi, same rd)'
    if a.op == 'SLLI' and 1 <= a.imm <= 3 and b.op == 'ADD' and uses and dead:
        return 'slli+add -> sh{1,2,3}add (Zba, dead)'
    if a.op == 'SLLI' and 1 <= a.imm <= 3 and b.op == 'ADD' and uses:
        return 'slli+add -> sh{1,2,3}add (Zba, rd1 live)'
    if a.op == 'ADDI' and b.op == 'ADDI' and dead and b.rs1 == a.rd:
        return 'addi+addi (same rd)'
    if a.op in ('ADD', 'ADDI', 'SLLI') and b.op in ('LW', 'LH', 'LHU', 'LB', 'LBU') and b.rs1 == a.rd:
        return 'addr-arith+load' + (' (dead)' if dead else ' (rd1 live)')
    if b.op in ('LW', 'LH', 'LHU', 'LB', 'LBU') and a.op in ('LW',) and b.rs1 == a.rd:
        return 'load+load (pointer chase)'
    if a.op in ('SLT', 'SLTU', 'SLTI', 'SLTIU') and b.op in ('BEQ', 'BNE') and a.rd in (b.rs1, b.rs2):
        return 'slt+branch'
    if a.op == 'MUL' and b.op in ('ADD', 'SRAI', 'SRLI', 'SRA', 'SRL') and uses:
        return 'mul+add/shift (fixed point)'
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--elf', required=True)
    ap.add_argument('--kernel-elf', required=True, help='kernel ELF with qos_disk_mailbox')
    ap.add_argument('--disk', required=True)
    ap.add_argument('--skip', type=int, default=0)
    ap.add_argument('--count', type=int, default=500000)
    ap.add_argument('--json')
    args = ap.parse_args()

    from chipformer.rv import elf as relf, ref
    from chipformer.rv import spec as S

    sy = symbols(args.kernel_elf)
    m = ref.Machine.from_program(relf.program(args.elf))
    dev = ReferenceDiskDevice(m, sy['qos_disk_mailbox'], Path(args.disk).read_bytes())

    per_op = collections.defaultdict(lambda: [0, 0])      # op -> [instr, tokens]
    per_tok = collections.Counter()                         # record length -> count
    pairs = collections.defaultdict(lambda: [0, 0, 0])      # kind -> [count, tokens_a+b, tokens_b]
    optpair = collections.defaultdict(lambda: [0, 0])       # (opA, opB) -> [count, tokens]
    refresh = 0
    valcls = collections.Counter()                          # value range of multi-token value records
    tot_i = tot_t = 0
    prev = None  # (pc, inst, ntok)
    t0 = time.time()
    n = args.skip + args.count
    for step in range(n):
        if m.halted:
            break
        pc = m.pc
        was_refresh = m.n == S.N_MAX
        word = m.rom[(pc - S.ROM_BASE) >> 2]
        ins = ref.decode(word)
        toks = m.record()
        dev.tick()
        if m.fault:
            raise SystemExit(f'guest fault {m.fault}')
        if step < args.skip:
            continue
        if was_refresh:  # an R refresh record: 1 token, no instruction
            refresh += 1
            tot_t += len(toks)
            prev = None
            continue
        nt = len(toks)
        tot_i += 1
        tot_t += nt
        per_op[ins.op][0] += 1
        per_op[ins.op][1] += nt
        per_tok[nt] += 1
        if nt in (2, 3) and S.family(toks[-1])[0] in ('F1', 'F2'):
            v = S.sign32(S.decode_value(toks))
            if nt == 2:
                cls = ('2tok pos 0x4000..0x7fff (RAM upper half)' if 0x4000 <= v < 0x8000 else
                       '2tok pos 0x8000..0x1ffff' if 0x8000 <= v < 0x20000 else
                       '2tok pos 0x20000..0x7ffff (DROM/ROM address)' if 0x20000 <= v < 0x80000 else
                       '2tok pos >= 0x80000' if v >= 0x80000 else '2tok negative')
            else:
                cls = '3tok (|v| >= 2^29)'
            valcls[cls] += 1
        if prev is not None and prev[0] + 4 == pc:
            k = pair_kind(prev[1], ins)
            if k:
                p = pairs[k]
                p[0] += 1
                p[1] += prev[2] + nt
                p[2] += nt
            o = optpair[(prev[1].op, ins.op)]
            o[0] += 1
            o[1] += prev[2] + nt
        prev = (pc, ins, nt)
    secs = time.time() - t0

    rep = dict(instructions=tot_i, tokens=tot_t, tok_per_instr=round(tot_t / max(tot_i, 1), 4),
               refresh_records=refresh, host_seconds=round(secs, 1),
               skip=args.skip, count=args.count, elf=str(args.elf))
    rep['by_op'] = {op: dict(instr=v[0], tokens=v[1], share_instr=round(v[0] / tot_i, 4),
                             share_tokens=round(v[1] / tot_t, 4), tok_per=round(v[1] / v[0], 3))
                    for op, v in sorted(per_op.items(), key=lambda kv: -kv[1][1])}
    rep['multi_token_value_classes'] = dict(valcls.most_common())
    rep['record_length_hist'] = dict(sorted(per_tok.items()))
    rep['fusion_candidates'] = {}
    for k, (c, tab, tb) in sorted(pairs.items(), key=lambda kv: -kv[1][1]):
        rep['fusion_candidates'][k] = dict(
            pairs=c, share_of_instr_covered=round(2 * c / tot_i, 4), tokens_in_pairs=tab,
            tokens_saved_if_fused_to_value_record=tab - tb,  # fused record = b's tokens (dead a)
            share_tokens_saved_value_record=round((tab - tb) / tot_t, 4),
            tokens_saved_if_fused_to_single_J_token=tab - 1 * c,  # in-circuit value write + J
            share_tokens_saved_single_token=round((tab - c) / tot_t, 4))
    rep['top_op_pairs'] = [dict(a=a, b=b, count=c, tokens=t, share_instr=round(2 * c / tot_i, 4))
                           for (a, b), (c, t) in sorted(optpair.items(), key=lambda kv: -kv[1][0])[:25]]
    extra = sum((k - 1) * c for k, c in per_tok.items() if k > 1)
    rep['extra_tokens_beyond_one_per_record'] = extra
    rep['share_extra_tokens'] = round(extra / tot_t, 4)
    out = json.dumps(rep, indent=1)
    print(out)
    if args.json:
        Path(args.json).write_text(out)


if __name__ == '__main__':
    main()
