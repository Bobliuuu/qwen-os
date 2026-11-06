#!/usr/bin/env python3
"""Run (part of) the real /bin/doomd DOOM engine INSIDE Qwenputer's merged Qwen checkpoint.

PREPARED, NOT RUN: needs a CUDA box with the merged checkpoint (confirm cost before launching).
Everything except the neural model itself is exercised by --dry-run, which uses the official
reference machine (chipformer.rv.ref.Machine) as the "model" and checks that the plan
(segments, breakpoints, byte stream) is self-consistent.

  PYTHONPATH=<qwenputer>/experimental/riscv python3 tools/model_doom_qwen.py \
      --elf build/qwenos-doomdmc.elf --disk <E1.img> --dry-run             # no GPU
  PYTHONPATH=... python3 tools/model_doom_qwen.py MODEL_DIR \
      --elf build/qwenos-doomdmc.elf --disk <E1.img> --target title-frame   # GPU

How it works (see chipformer/rv/chat.py, bridge.py)
  * The merged model runs a firmware that is a *snapshot of machine state* (core.snapshot:
    pc, regs, 32 KB RAM, ROM, DROM).  The snapshot need not be a boot image: the host advances
    the official reference machine (proven identical to our C twin by tools/upstream_doomd.py)
    to a chosen instruction, and the model resumes there.
  * Each segment is one Qwen turn: Qwen writes a <tool_call>, the circuit predicts GO and the
    chip layers execute the guest (one chip token per ~0.74 instruction), until HALT.
  * Stop points are ROM breakpoints: the ROM word at the stop pc is replaced by
    `ebreak`, so the circuit emits a fault record and HALTs exactly there.  A stop is
    a frame marker (console byte 0x02) or, with disk pausing (default), a published disk request.
  * Disk servicing = pause/patch/resume: at a disk-request stop the host truth machine serves the
    request exactly as tools/upstream_doomd.py does (one-instruction latency), and the NEXT
    segment starts from the truth state (response bytes patched into RAM): a fresh
    core.snapshot + new Qwen turn.  The host executes ONE instruction per segment beyond the
    model (so a breakpoint at the same pc cannot fire at once); every other instruction result
    is a chip token compared against the lockstep oracle.
  * Lockstep oracle: bridge.Session on a copy of the same patched machine; chat.generate(lock=)
    stops at the first token that differs from the reference.  After each segment we also
    require: oracle instruction count == truth count (+2 for the breakpoint pair) and that the
    model's BYTE tokens equal the truth console bytes.
  * max_chip is raised per segment to 1.25 x the planned token count + 1000.

Chip-token cost (measured on the real doomd ELF with upstream reference records)
  1.351 tok/instr over the first 12M instructions (not 1.44).
  PLUS one full-Qwen text token per console byte: every putc is echoed as a Qwen text token
  (bridge.Session.run), which runs all Qwen layers.  The 'p' LCD dump is ~78,000 bytes per frame,
  so a dumped frame costs ~78k full text tokens (tens of minutes on an L4), far more than the
  ~9k chip tokens of a title-loop frame.  The trace is complete (every instruction result is a
  token checked against the reference), so a NON-dumped frame whose 0x02 marker comes out is
  full evidence; render the picture from the oracle/C twin.  --dump arms 'p' only if you
  want pixels from the model's own bytes.

Cheapest strategy (numbers: tools/rv32_fast + disk log, E1.img, freedoom1.wad)
  1. title-frame (default): snapshot right after marker #2 (instr 6,743,480; boot, title
     picture and menu setup skipped).  The next frame ends 6,634 instr later with ZERO disk
     reads: ~9k chip tokens, 1 text token, a few seconds on the 3,200 tok/s executor.  One
     genuine engine frame, no pauses.  Recommended first GPU run.
  2. title-frame --dump: same plus ~78k byte-echo text tokens (30-60 min on an L4).
  3. game-frame: the first level frame is marker #343 at instr 16,344,926 (NOT ~11.3M; title
     loop ends at 9.50M, level load + first render is 6.84M more).  From a snapshot at marker
     342: 6.84M instr = ~9.2M chip tokens (~48 min at 3,200 tok/s; ~10 h on the HF path at
     ~250 tok/s) plus ~5,150 disk requests, each a pause (new snapshot, ROM/DROM table
     rebuild, new Qwen turn, seconds each).  Later frames: 4.4-6.3M instr and 2.7-5.1k
     requests EACH.  Do not try before (1).
  Reducing pauses would need guest-side batching (256-byte windows, sector cache; ports/doomdmc/
  qnor.c / kernel) - not done here.  Unique data per game frame is 120-160 KB, more than the
  128 KB DROM, so the disk cannot simply be baked into the snapshot's DROM.
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from upstream_ref import symbols, ReferenceDiskDevice
from upstream_doomd import MarkerParser

EBREAK = 0x00100073  # the breakpoint: the circuit emits a fault record and HALTs


def clone(m):
    """Copy of a ref.Machine's committed state (ROM/RAM lists, regs, anchor, digit file)."""
    from chipformer.rv import ref
    c = ref.Machine(list(m.rom), list(m.ram), list(m.x), m.anchor, m.n, False, m.steps, m.drom,
                    [list(r) for r in m.bn])
    c.out = bytearray(m.out)
    return c


def breakpoint_at(m, pc):
    from chipformer.rv import spec as S
    i = (pc - S.ROM_BASE) >> 2
    m.rom[i] = EBREAK


class Truth:
    """The official reference machine + block device + key injection: the host's view."""

    def __init__(self, elf, disk, kelf, keys, disk_pause):
        from chipformer.rv import elf as relf, ref
        sy = symbols(kelf)
        self.kbox, self.dbox = sy['qos_input_mailbox'], sy['qos_disk_mailbox']
        self.m = ref.Machine.from_program(relf.program(elf))
        self.dev = ReferenceDiskDevice(self.m, self.dbox, disk)
        self.par, self.seen, self.marks, self.kseq = MarkerParser(), 0, [], 100
        self.keys = [[c, int(n), False] for c, n in keys]
        self.disk_pause = disk_pause
        self.tokens = 1

    def step(self):
        """One record; returns 'disk' / 'marker' / None for the event it caused."""
        m = self.m
        self.last_pc = m.pc
        t = m.record()
        self.last_len = len(t)
        self.tokens += len(t)
        if m.fault:
            raise RuntimeError(f'guest fault {m.fault}')
        nreads = len(self.dev.reads)
        self.dev.tick()
        ev = 'disk' if self.disk_pause and len(self.dev.reads) != nreads else None
        if len(m.out) != self.seen:
            for c in m.out[self.seen:]:
                if self.par.feed(c):
                    self.marks.append(m.steps - 1)
                    ev = ev or 'marker'
                    for k in self.keys:
                        if not k[2] and len(self.marks) >= k[1]:
                            k[2] = True
                            m.ram[(self.kbox + 4) // 4] = ord(k[0])
                            m.ram[self.kbox // 4] = self.kseq
                            self.kseq += 1
                            break
            self.seen = len(m.out)
        return ev


def oracle_run(machine, max_records=10**8):
    """Host stand-in for one model segment: GO .. HALT on the reference.
    Returns (instructions, chip tokens, console bytes)."""
    machine.halted = False
    s0, o0, toks = machine.steps, len(machine.out), 0
    for _ in range(max_records):
        toks += len(machine.record())
        if machine.halted:
            break
    else:
        raise RuntimeError('oracle did not halt')
    return machine.steps - s0, toks, bytes(machine.out[o0:])


def plan(truth, args):
    """Yield segments: dict(start=patched Machine, stop_pc, instr, tokens, out, reason)."""
    m = truth.m
    # Phase 0: host runs to the snapshot point (marker --snapshot-marker; 'p' injected there).
    while len(truth.marks) < args.snapshot_marker:
        truth.step()
    target = args.snapshot_marker + args.frames
    if any(not k[2] for k in truth.keys):
        raise RuntimeError('a key would be injected inside a model segment (the model could not see it)')
    nseg = 0
    while len(truth.marks) < target:
        start = clone(m)
        s0, t0, o0 = m.steps, truth.tokens, len(m.out)
        ev, visited = None, set()
        while len(truth.marks) < target:
            pc = m.pc
            ev = truth.step()
            if ev == 'disk':
                # stop BEFORE the store that published the request: the model halts at pc, the host
                # executes the store (+ the device's reply) and the next segment starts after it
                stop_pc, instr = pc, m.steps - s0 - 1
                tokens = truth.tokens - t0 - truth.last_len
                if pc in visited:
                    raise RuntimeError(f'disk-request store {pc:#x} already executed in the segment')
                break
            visited.add(pc)
            if args.max_instructions and m.steps - s0 > args.max_instructions:
                raise RuntimeError('segment exceeds --max-instructions')
        else:
            # frame marker: stop at the first pc after it that the segment has not executed (the
            # instruction after a putc ecall sits in a shared putc(); any byte would fire there).
            # Extra host instructions are part of the segment (the model runs them too).
            for _ in range(20000):
                if m.pc not in visited:
                    break
                visited.add(m.pc)
                truth.step()
            else:
                raise RuntimeError('no fresh breakpoint pc found')
            stop_pc, instr, tokens = m.pc, m.steps - s0, truth.tokens - t0
        breakpoint_at(start, stop_pc)
        nseg += 1
        yield dict(index=nseg, start=start, start_steps=s0, stop_pc=stop_pc, instr=instr,
                   tokens=tokens, out=bytes(m.out[o0:]),
                   reason='disk' if ev == 'disk' else 'marker')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('model', nargs='?', help='merged Qwenputer checkpoint dir (omit with --dry-run)')
    ap.add_argument('--elf', default='build/qwenos-doomdmc.elf')
    ap.add_argument('--kernel-elf', default=None)
    ap.add_argument('--disk', required=True, help='E1.img block device (served by the host)')
    ap.add_argument('--target', choices=['boot-frame', 'title-frame', 'game-frame'], default='title-frame')
    ap.add_argument('--snapshot-marker', type=int, default=None,
                    help='frame markers the host runs before the snapshot '
                         '(default: boot-frame 0, title-frame 100, game-frame 342; numbers for the 2026-11-03 build)')
    ap.add_argument('--frames', type=int, default=1, help='frames the model must complete')
    ap.add_argument('--dump', action='store_true',
                    help="arm the 'p' full-frame LCD dump (~78k extra full-model text tokens)")
    ap.add_argument('--no-disk-pause', action='store_true',
                    help='never stop for disk requests (valid only if the span reads nothing)')
    ap.add_argument('--max-segments', type=int, default=100000)
    ap.add_argument('--max-instructions', type=int, default=0, help='per-segment host cap')
    ap.add_argument('--max-chip', type=int, default=0,
                    help='per-segment chip-token cap (default 1.25 x planned tokens + 1000)')
    ap.add_argument('--max-text', type=int, default=0,
                    help='per-segment text-token cap (default tool call + byte echoes + 400)')
    ap.add_argument('--no-executor', action='store_true', help='HF chip layers (~250 tok/s), not the executor')
    ap.add_argument('--out', default='model_doom_out.bin', help='console bytes the run produced')
    ap.add_argument('--tok-per-s', type=float, default=3200.0, help='for the time estimate only')
    ap.add_argument('--dry-run', action='store_true', help='reference machine stands in for the model')
    args = ap.parse_args()
    if args.snapshot_marker is None:
        # markers seen before the snapshot; verify with the rv32_fast "frame N at" log for YOUR elf
        args.snapshot_marker = {'boot-frame': 0, 'title-frame': 100, 'game-frame': 342}[args.target]
    if not args.dry_run and not args.model:
        ap.error('model dir required unless --dry-run')
    try:
        import chipformer.rv.ref  # noqa
    except ImportError as e:
        sys.exit('set PYTHONPATH to qwenputer/experimental/riscv: ' + str(e))
    kelf = args.kernel_elf or str(Path(args.elf).with_name('kernel-doomd.elf'))
    if args.dump and args.snapshot_marker < 1:
        ap.error("--dump injects 'p' at the snapshot marker, which must be >= 1")
    keys = [('p', args.snapshot_marker)] if args.dump else []
    truth = Truth(args.elf, Path(args.disk).read_bytes(), kelf, keys, not args.no_disk_pause)

    chat = bridge = S = ids = None
    if not args.dry_run:
        from chipformer.rv import bridge, chat as chatmod, spec as S
        import torch
        chat = chatmod.RvChat(args.model, fast=not args.no_executor,
                              executor=(torch.cuda.is_available() and not args.no_executor))
        ids = chat.prompt_ids([{'role': 'user', 'content': 'Use calc to evaluate 1 + 1.'}])

    class SegmentDone(Exception):
        pass

    produced, tot_i, tot_t, tot_text, nseg, t0 = bytearray(), 0, 0, 0, 0, time.time()
    model_chip = 0
    for seg in plan(truth, args):
        nseg += 1
        if nseg > args.max_segments:
            sys.exit(f'--max-segments {args.max_segments} reached (segments are expensive)')
        oracle = clone(seg['start'])
        if args.dry_run:
            i, t, out = oracle_run(oracle)
            ok = (i == seg['instr'] + 1 and out == seg['out'])
        else:
            cpu = clone(seg['start'])
            lock = bridge.Session(chat.T, oracle)
            lock.history(ids)
            got, st = bytearray(), dict(halt=False, chip=0, text=0)

            def on_token(nxt):
                if nxt >= chat.v0:
                    st['chip'] += 1
                    fam, p = S.family(nxt - chat.v0)
                    if fam == 'BYTE' and p < 256:
                        got.append(p)
                    if fam == 'HALT':
                        st['halt'] = True
                else:
                    st['text'] += 1
                    if st['halt']:
                        raise SegmentDone  # the NL after HALT: segment finished
            max_chip = args.max_chip or int(seg['tokens'] * 1.25) + 1000
            max_text = args.max_text or (len(seg['out']) + 400)
            try:
                res = chat.generate(ids, cpu, max_new=max_text, max_chip=max_chip, check_head=True,
                                    lock=lock, on_token=on_token, verbose=False)
                if res['lock_error'] is not None:
                    sys.exit(f"segment {nseg}: model diverged from reference: {res['lock_error']}")
                if not st['halt']:
                    sys.exit(f'segment {nseg}: no HALT within max_chip={max_chip}/max_text={max_text}')
            except SegmentDone:
                pass
            ok = (st['halt'] and bytes(got) == seg['out']
                  and oracle.steps - seg['start_steps'] == seg['instr'] + 1)
            model_chip += st['chip']; tot_text += st['text']
        tot_i += seg['instr']; tot_t += seg['tokens']
        produced += seg['out']
        if not ok:
            sys.exit(f"segment {nseg} FAILED consistency check ({seg['reason']}, stop_pc {seg['stop_pc']:#x})")
        if nseg <= 3 or nseg % 200 == 0:
            print(f'seg {nseg} {seg["reason"]} instr={seg["instr"]} tokens={seg["tokens"]} '
                  f'stop_pc={seg["stop_pc"]:#x} ok ({time.time()-t0:.0f}s)', flush=True)
    Path(args.out).write_bytes(bytes(produced))
    print(json.dumps(dict(
        mode='dry-run (reference stand-in, NOT the model)' if args.dry_run else 'MODEL', target=args.target,
        snapshot_marker=args.snapshot_marker, frames=args.frames, segments=nseg,
        instructions=tot_i, planned_chip_tokens=tot_t, tok_per_instr=round(tot_t / max(tot_i, 1), 4),
        model_chip_tokens=model_chip, model_text_tokens=tot_text,
        console_bytes=len(produced), extra_full_text_tokens_for_echo=len(produced),
        est_chip_seconds=round(tot_t / args.tok_per_s, 1), tok_per_s_assumed=args.tok_per_s,
        frame_markers_in_output=produced.count(b'\x02'), out=args.out), indent=2))


if __name__ == '__main__':
    main()
