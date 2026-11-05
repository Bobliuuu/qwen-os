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
    chip layers execute the guest (~1.35 chip tokens per instruction), until HALT.
  * Stop points are ROM breakpoints: the ROM word at the stop pc is replaced by
    `ebreak`, so the circuit emits a fault record and HALTs exactly there.  A stop is
    a frame marker (console byte 0x02) or, with disk pausing (default), a published disk request.
  * Disk servicing = pause/patch/resume: at a disk-request stop the host truth machine serves the
    request exactly as tools/upstream_doomd.py does (one-instruction latency), and the NEXT
    segment starts from the truth state (response bytes patched into RAM): a fresh
    core.snapshot + new Qwen turn.  The model stops BEFORE the store that publishes the request
    (breakpoint there); the host executes that one store per segment, every other instruction
    result is a chip token compared against the lockstep oracle.  Marker stops are placed at the
    first pc after the marker that the segment has not yet executed (putc() is shared).
  * Lockstep oracle: bridge.Session on a copy of the same patched machine; chat.generate(lock=)
    stops at the first token that differs from the reference.  After each segment we also
    require: oracle instruction count == truth count (+1 for the ebreak) and that the
    model's BYTE tokens equal the truth console bytes.
  * max_chip is raised per segment to 1.25 x the planned token count + 1000.

Chip-token cost (measured on the real doomd ELF, md5 80ac7df8..., with upstream reference records)
  1.35 tok/instr (1.352 over the first 18M instructions of the previous build; 1.344-1.353 per
  target below); not the 1.44 of the C benchmarks.
  PLUS one full-Qwen text token per console byte: every putc is echoed as a Qwen text token
  (bridge.Session.run) that runs ALL Qwen layers.  A frame with the 'p' LCD dump costs ~4.98M
  instr (~6.7M chip tokens) and 78,115 console bytes (78k full text tokens, tens of minutes on
  an L4): ~750x the cost of the same frame without the dump.  The trace is complete (every
  instruction result is a token checked against the reference), so a NON-dumped frame whose
  0x02 marker comes out is full evidence; render pixels from the C twin / oracle RAM.

Targets and cost (this build, E1.img + freedoom1 data; 3,200 tok/s executor figure from the
upstream docs for an L4, ~250 tok/s on the HF path; dry-run totals are exact, time is an estimate):
  title-frame  idle title-loop frame after 100 markers: 6,563 instr, 9,988 chip tokens, 1 text token,
               0 disk requests, ~3 s.  NOTE this frame draws nothing (no pump); it only proves
               engine tics run in the model.
  boot-frame   reset -> first frame marker (title picture is drawn): 1,552,672 instr, ~2.09M chip
               tokens (~11 min), 292 segments (disk pauses), 661 console bytes (kernel boot text,
               661 text tokens).  Cheapest frame that draws pixels; the snapshot IS the unmodified
               ELF (no host pre-run).  Recommended first GPU run after a smoke test.
  game-frame   first level frame (marker #342): 5,842,573 instr, 7,907,244 chip tokens (~41 min at
               3,200 tok/s, ~9 h on the HF path), 5,151 segments (one per disk request; each
               = snapshot + Qwen turn, ROM/DROM table rebuild, ~seconds, so 1-3 h of overhead).
               Later game frames: 4.7-6.1M instr and 3.8-5.8k requests EACH, 140-160 KB of
               unique disk data per frame (more than the 128 KB DROM, so the disk cannot
               simply be baked into the snapshot).  Do boot-frame first.
  Strategy: skip the title (snapshot), never dump, W8-style strips are moot without a dump, and
  reduce pauses (a 256-byte window + sector cache in the guest, ports/doomdmc/qnor.c / kernel;
  not done here) before attempting game frames.
  Marker numbers shift with every rebuild of the engine: re-read them from
  `build/rv32_fast <elf> <img> 100 108 out.bin N` ("frame K at"), and pass --snapshot-marker.
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

    def __init__(self, elf, disk, kelf, keys, disk_pause, rom_plan=None, sym_elf=None):
        from chipformer.rv import elf as relf, ref
        sy = symbols(kelf)
        self.kbox, self.dbox = sy['qos_input_mailbox'], sy['qos_disk_mailbox']
        self.m = ref.Machine.from_program(relf.program(elf))
        self.dev = ReferenceDiskDevice(self.m, self.dbox, disk)
        self.par, self.seen, self.marks = MarkerParser(), 0, []
        self.keys = [[c, int(n), False] for c, n in keys]
        self.disk_pause = disk_pause
        self.tokens = 1
        # chunk ROM (tools/chunkrom.py): the host fills the data-ROM window of the ROM chunk that contains the
        # current frame-marker count; the guest (-DQ_CHUNKROM build) then serves those disk reads from ROM.
        self.disk_bytes = disk
        self.rom_chunks = rom_plan['chunks'] if rom_plan else []
        self.rom_base = rom_plan['base'] if rom_plan else None
        self.rom_cur = None            # index of the chunk whose window is installed (None = cleared)
        # stop hook (qlcd.c q_stop_in / q_stop_here, -DQ_CHUNKROM builds): lets a multi-frame segment end at ANY frame
        # marker at a pc that is fresh for the segment (the shared frame-end code never is). Needs engine symbols.
        self.hook_at = self.hook_pc = self.hook_fr = None
        self.fr_off = None
        if sym_elf:
            sy_e = symbols(sym_elf)
            self.hook_at, self.hook_pc, self.hook_fr = (sy_e.get('q_stop_at'), sy_e.get('q_stop_here'), sy_e.get('q_frames'))
            if self.hook_pc is None or self.hook_at is None or self.hook_fr is None:
                self.hook_pc = None
        self.armed = False

    def rom_index(self):
        """ROM chunk containing the current frame-marker count (chunks are [lo, hi) marker counts)."""
        n = len(self.marks)
        for i, c in enumerate(self.rom_chunks):
            if c['lo'] <= n < c['hi']:
                return i
        return None

    def apply_rom_window(self):
        """Install (fill_drom) or clear the window for the chunk containing the marker count on the truth machine.
        Called only at a segment boundary, BEFORE the segment's start snapshot is cloned, so the model's
        snapshot (core.snapshot -> DROM tables) and the oracle clone both contain it."""
        if not self.rom_chunks:
            return
        i = self.rom_index()
        if i == self.rom_cur:
            return
        import chunkrom
        if i is None:
            chunkrom.clear_drom(self.m, self.rom_base)
        else:
            ext = [tuple(e) for e in self.rom_chunks[i]['extents']]
            chunkrom.fill_drom(self.m, ext, self.disk_bytes, self.rom_base)
        self.rom_cur = i

    def boundaries(self, split_set):
        b = set(split_set) | {c['lo'] for c in self.rom_chunks if c['lo'] > 0} | {k[1] for k in self.keys if not k[2]}
        return sorted(b)

    def arm_stop(self, split_set, target):
        """At a segment boundary: arm q_stop_at so the segment ends right after the next ROM/split/key boundary marker
        (hook mode). The guest counts markers in q_frames (incremented before the marker byte); fr_off = host marker
        count - q_frames is constant and is read the first time we are between markers (any segment start is)."""
        self.armed = False
        if self.hook_pc is None:
            return
        n = len(self.marks)
        if n == 0:
            return   # cold boot: takeover zeroes the guest RAM (incl. q_stop_at) when doomd starts; the first marker ends the segment the old way
        if self.fr_off is None:
            self.fr_off = n - self.m.ram[self.hook_fr // 4]
        nb = [b for b in sorted(set(self.boundaries(split_set)) | {target}) if n < b <= target]
        v = (nb[0] - self.fr_off) if nb else 0
        self.m.ram[self.hook_at // 4] = v
        self.armed = bool(v)

    def rom_boundary_due(self):
        """True once the tic counter has left the installed chunk (the segment must end soon so the next
        one starts with the right window; only checked at frame markers)."""
        return bool(self.rom_chunks) and self.rom_index() != self.rom_cur

    def key_pending(self):
        return any(not k[2] and len(self.marks) >= k[1] for k in self.keys)

    def inject_due(self):
        """Host key injection at a SEGMENT BOUNDARY (never inside a model segment): write at most one due
        key into the input mailbox (char, then seq).  Keys are (char, marker_count) = injected at the first
        boundary after that many frame markers.  Both the model's start snapshot and the oracle copy are
        cloned after this write, so every chunk sees the same schedule."""
        for k in self.keys:
            if not k[2] and len(self.marks) >= k[1]:
                k[2] = True
                # key ring {u32 seq; u8 q[4]} at the input mailbox: byte into q[seq & 3], then seq+1 LAST (os.patch)
                seq = self.m.ram[self.kbox // 4]
                qa = self.kbox + 4 + (seq & 3)
                w = self.m.ram[qa // 4]
                sh = (qa & 3) * 8
                self.m.ram[qa // 4] = (w & ~(0xff << sh) & 0xffffffff) | (ord(k[0]) << sh)
                self.m.ram[self.kbox // 4] = (seq + 1) & 0xffffffff
                return True
        return False

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
    truth.inject_due()
    nseg = 0
    while len(truth.marks) < target:
        truth.inject_due()
        if truth.hook_pc is not None and m.pc == truth.hook_pc:
            truth.step()  # leave the stop hook's entry pc on the host so a breakpoint on it can fire in this segment
        truth.apply_rom_window()
        truth.arm_stop(getattr(args, 'split_set', ()), target)
        start = clone(m)
        s0, t0, o0 = m.steps, truth.tokens, len(m.out)
        ev, visited, hooked = None, set(), False
        cold = truth.hook_pc is not None and not truth.marks
        sstep = next((x for x in getattr(args, 'split_steps', ()) if x > s0), None)   # absolute instruction count to split at
        while len(truth.marks) < target or truth.armed:
            pc = m.pc
            if truth.armed and pc == truth.hook_pc and m.steps > s0:
                # the guest, with the marker count at the boundary, is about to run q_stop_here (start of the next frame end): stop BEFORE it
                ev, hooked = 'split', True
                stop_pc, instr, tokens = pc, m.steps - s0, truth.tokens - t0
                break
            if sstep is not None and m.steps >= sstep and pc not in visited and m.steps > s0:
                # instruction-count split (cold boot / level load): stop BEFORE the first pc at/after sstep that this segment has
                # not executed yet (an ebreak fires on the first execution of its pc, so the stop pc must be fresh)
                ev, hooked = 'isplit', True
                stop_pc, instr, tokens = pc, m.steps - s0, truth.tokens - t0
                break
            ev = truth.step()
            if ev == 'marker' and cold:
                ev = 'split'  # cold boot: end at the first marker (a lone marker in the segment: its next pc is fresh)
                break
            if ev == 'marker' and truth.key_pending():
                break  # a due key is injected at this boundary: end the segment at the marker
            if ev == 'marker' and truth.hook_pc is None and truth.rom_boundary_due():
                ev = 'rom'  # the marker count left the installed ROM chunk: end the segment at this marker
                break
            if ev == 'marker' and truth.hook_pc is None and len(truth.marks) in getattr(args, 'split_set', ()):
                ev = 'split'  # explicit segment boundary (model-chunk start, tools/model_runplan.py)
                break
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
        if ev != 'disk' and not hooked:
            # frame marker: stop at the first pc after it that the segment has not executed (the
            # instruction after a putc ecall sits in a shared putc(); any byte would fire there).
            # Extra host instructions are part of the segment (the model runs them too).
            for _ in range(20000):
                if m.pc not in visited:
                    break
                visited.add(m.pc)
                if truth.step() == 'disk':
                    raise RuntimeError('disk request while advancing to a fresh breakpoint pc (ROM-chunk boundary): '
                                       'shift the chunk boundary or add margin to the extents')
            else:
                raise RuntimeError('no fresh breakpoint pc found')
            stop_pc, instr, tokens = m.pc, m.steps - s0, truth.tokens - t0
        breakpoint_at(start, stop_pc)
        nseg += 1
        yield dict(index=nseg, start=start, start_steps=s0, stop_pc=stop_pc, instr=instr,
                   tokens=tokens, out=bytes(m.out[o0:]),
                   reason={'disk': 'disk', 'rom': 'rom', 'split': 'split', 'isplit': 'isplit'}.get(ev, 'marker'), rom_chunk=truth.rom_cur, markers=bytes(m.out[o0:]).count(b'\x02'))
    left = [k[0] for k in truth.keys if not k[2]]
    if left:
        raise RuntimeError(f'keys {left!r} were never injected: a key must be due before the final marker so that it falls on a '
                           'segment boundary (keys cannot be typed inside a model segment)')


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
    ap.add_argument('--k-graph', type=int, default=64, help='K>1 (default 64; 0 or 1 = old per-token loop): K executor tokens per CUDA graph with bulk lockstep verification (tools/kgraph.py)')
    ap.add_argument('--k-pipe', action='store_true', help='with --k-graph: launch block i+1 before syncing block i (speculative on the oracle tokens; every block is still verified)')
    ap.add_argument('--fast-kernels', action='store_true', help='split/fused Triton executor kernels (needs the patched tritonexec.py of perf/ktoken: tools/tritonexec_fast.py shipped in qwenputer/chipformer/rv)')
    ap.add_argument('--no-executor', action='store_true', help='HF chip layers (~250 tok/s), not the executor')
    ap.add_argument('--out', default='model_doom_out.bin', help='console bytes the run produced')
    ap.add_argument('--tok-per-s', type=float, default=3200.0, help='for the time estimate only')
    ap.add_argument('--segment-range', default=None, metavar='A:B',
                    help='model-verify only segments A..B-1 (1-based index A, exclusive B); the host reference still '
                         'fast-forwards through the others (chunked/parallel verification, see model_doom_chunks.py)')
    ap.add_argument('--keys', default='', help="key schedule 'CHAR@MARKERS,...' (e.g. 'p@3,\\n@10'): CHAR is typed (written to "
                    "the input mailbox) at the first segment boundary after that many frame markers; \\n \\r \\s=space escapes")
    ap.add_argument('--rom-plan', default=None, metavar='JSON', help='chunk-ROM plan from tools/chunkrom.py --json (needs the '
                    '-DQ_CHUNKROM ELF): the host installs each ROM chunk\'s disk-extent window in the snapshot DROM so reads inside it never '
                    'pause; segments are split at ROM-chunk boundaries (also honored by --segment-range and --plan-json)')
    ap.add_argument('--sym-elf', default=None, help='engine ELF with symbols (q_stop_in/q_stop_here) for the segment stop hook; '
                    'without it segments can only end at markers whose next pc is fresh')
    ap.add_argument('--split-steps', default='', help='comma list of absolute instruction counts: a segment ends at the first pc not yet executed in it at/after each '
                    '(splits the cold-boot/level-load stretch, where no frame marker exists, into model chunks)')
    ap.add_argument('--lock-max-records', type=int, default=10**9,
                    help='per-segment instruction limit of the lockstep oracle (upstream default 1e6 is too small for zero-pause segments)')
    ap.add_argument('--split-markers', default='', help='comma list of frame-marker counts at which a segment must end (so a\n                    '
                    'model chunk can start there: --segment-range then selects segments between such boundaries)')
    ap.add_argument('--plan-json', default=None, help='write per-segment plan (instr, tokens, bytes) and exit')
    ap.add_argument('--result-json', default=None, help='write the final report here too')
    ap.add_argument('--dump-starts', default=None, metavar='DIR', help='[modal staging] host-only: one pass over the reference machine, '
                    'pickle every segment (start machine + expected outputs) to DIR/seg<N>.pkl, then exit')
    ap.add_argument('--load-starts', default=None, metavar='DIR', help='[modal staging] take segments from DIR/seg<N>.pkl instead of replaying the host '
                    '(needs --segment-range A:B)')
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
    for tok in filter(None, args.keys.split(',')):
        c, n = tok.rsplit('@', 1)
        keys.append(({'\\n': '\n', '\\r': '\r', '\\s': ' '}.get(c, c), int(n)))
    args.split_set = {int(x) for x in args.split_markers.split(',') if x}
    args.split_steps = sorted(int(x) for x in args.split_steps.split(',') if x)
    rom_plan = json.loads(Path(args.rom_plan).read_text()) if args.rom_plan else None
    truth = Truth(args.elf, Path(args.disk).read_bytes(), kelf, keys, not args.no_disk_pause, rom_plan, args.sym_elf)

    chat = bridge = S = ids = None
    if not args.dry_run:
        from chipformer.rv import bridge, chat as chatmod, spec as S
        import torch
        # upstream bridge.Session runs the lockstep oracle for a whole segment in ONE call limited to 1e6 records
        # (instructions); chunk-ROM segments are whole frames (2.5M+ instr), so raise the limit (python ref ~100k instr/s).
        bridge.Session.qwen.__defaults__ = (args.lock_max_records, True)
        bridge.Session.run.__defaults__ = (args.lock_max_records,)
        if args.fast_kernels:
            from chipformer.rv import tritonexec as _tx
            for k_, v_ in dict(SPLIT=True, CH=16, GW=4, H2W=4, BLOCK=4, FW=1, FUSE=True).items():
                setattr(_tx.Executor2, k_, v_)
        if args.k_graph > 1:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import kgraph
            kgraph.install(chatmod, args.k_graph, pipe=args.k_pipe)
        chat = chatmod.RvChat(args.model, fast=not args.no_executor,
                              executor=(torch.cuda.is_available() and not args.no_executor))
        ids = chat.prompt_ids([{'role': 'user', 'content': 'Use calc to evaluate 1 + 1.'}])

    class SegmentDone(Exception):
        pass

    ra, rb = 1, 10**9
    if args.segment_range:
        ra, rb = (int(x) for x in args.segment_range.split(':'))
    if args.plan_json:
        segs = [dict(index=g['index'], instr=g['instr'], tokens=g['tokens'], out=len(g['out']),
                     reason=g['reason'], stop_pc=g['stop_pc'], markers=g['markers'], rom_chunk=g['rom_chunk']) for g in plan(truth, args)]
        Path(args.plan_json).write_text(json.dumps(segs))
        print(f'planned {len(segs)} segments, {sum(g["instr"] for g in segs)} instr, '
              f'{sum(g["tokens"] for g in segs)} tokens')
        return
    produced, tot_i, tot_t, tot_text, nseg, t0 = bytearray(), 0, 0, 0, 0, time.time()
    model_chip = 0
    nver = 0
    model_secs = 0.0
    t_chipsum = t_textsum = 0.0
    detail = []
    reasons = {}
    def _loaded():
        import pickle, os
        for n in range(ra, rb):
            p = Path(args.load_starts) / f'seg{n}.pkl'
            while not p.exists():
                time.sleep(15)
                if hasattr(args, 'reload_hook'):
                    args.reload_hook()
            yield pickle.loads(p.read_bytes())
    if args.dump_starts:
        import pickle, os
        Path(args.dump_starts).mkdir(parents=True, exist_ok=True)
        for seg in plan(truth, args):
            tmp = Path(args.dump_starts) / f'.seg{seg["index"]}.tmp'
            tmp.write_bytes(pickle.dumps(seg, protocol=5))
            os.replace(tmp, Path(args.dump_starts) / f'seg{seg["index"]}.pkl')
            print(f'dumped seg {seg["index"]} instr={seg["instr"]} steps={seg["start_steps"]} ({time.time()-t0:.0f}s)', flush=True)
        print('DUMP_DONE', flush=True)
        return
    if args.load_starts:
        assert args.segment_range, '--load-starts needs --segment-range'
        nseg = ra - 1
    for seg in (_loaded() if args.load_starts else plan(truth, args)):
        nseg += 1
        if not (ra <= nseg < rb):
            continue  # host-only fast-forward: another chunk verifies this segment
        nver += 1
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
            tg = time.time()
            try:
                res = chat.generate(ids, cpu, max_new=max_text, max_chip=max_chip, check_head=True,
                                    lock=lock, on_token=on_token, verbose=False)
                t_chipsum += res['chip_seconds']; t_textsum += res['text_seconds']
                if res['lock_error'] is not None:
                    sys.exit(f"segment {nseg}: model diverged from reference: {res['lock_error']}")
                if not st['halt']:
                    sys.exit(f'segment {nseg}: no HALT within max_chip={max_chip}/max_text={max_text}')
            except SegmentDone:
                pass
            model_secs += time.time() - tg
            ok = (st['halt'] and bytes(got) == seg['out']
                  and oracle.steps - seg['start_steps'] == seg['instr'] + 1)
            model_chip += st['chip']; tot_text += st['text']
        detail.append([nseg, bool(ok), seg['markers'], seg['instr'], seg['tokens']])
        reasons[seg['reason']] = reasons.get(seg['reason'], 0) + 1
        tot_i += seg['instr']; tot_t += seg['tokens']
        produced += seg['out']
        if not ok:
            sys.exit(f"segment {nseg} FAILED consistency check ({seg['reason']}, stop_pc {seg['stop_pc']:#x})")
        if nseg <= 3 or nseg % 200 == 0:
            print(f'seg {nseg} {seg["reason"]} instr={seg["instr"]} tokens={seg["tokens"]} '
                  f'stop_pc={seg["stop_pc"]:#x} ok ({time.time()-t0:.0f}s)', flush=True)
    Path(args.out).write_bytes(bytes(produced))
    import socket
    try:
        import torch
        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'
    except Exception:
        gpu = 'none'
    wall = max(model_secs, 1e-9) if not args.dry_run else max(time.time() - t0, 1e-9)
    rep = dict(
        k_graph=args.k_graph, gpu_mem_peak_mb=(round(__import__('torch').cuda.max_memory_allocated() / 2**20) if not args.dry_run else None),
        kgraph_stats=(__import__('kgraph').STATS if args.k_graph > 1 and not args.dry_run else None),
        gen_chip_seconds=None if args.dry_run else round(t_chipsum, 2), gen_text_seconds=None if args.dry_run else round(t_textsum, 2),
        host=socket.gethostname(), model_seconds=round(model_secs, 1), gpu=gpu, executor=not args.no_executor, keys=args.keys,
        chip_tokens_per_s=round(model_chip / wall, 1), instr_per_s=round(tot_i / wall, 1),
        mode='dry-run (reference stand-in, NOT the model)' if args.dry_run else 'MODEL', target=args.target,
        segment_range=args.segment_range, wall_seconds=round(time.time() - t0, 1),
        snapshot_marker=args.snapshot_marker, frames=args.frames, segments=nver, total_segments=nseg, first_segment=ra,
        instructions=tot_i, planned_chip_tokens=tot_t, tok_per_instr=round(tot_t / max(tot_i, 1), 4),
        model_chip_tokens=model_chip, model_text_tokens=tot_text,
        console_bytes=len(produced), extra_full_text_tokens_for_echo=len(produced),
        est_chip_seconds=round(tot_t / args.tok_per_s, 1), tok_per_s_assumed=args.tok_per_s,
        frame_markers_in_output=produced.count(b'\x02'), out=args.out,
        segments_by_reason=reasons, rom_plan=args.rom_plan,
        segment_detail=detail)  # [index, ok, markers, instr, planned_tokens]
    print(json.dumps(rep, indent=2))
    if args.result_json:
        Path(args.result_json).write_text(json.dumps(rep, indent=2))


if __name__ == '__main__':
    main()
