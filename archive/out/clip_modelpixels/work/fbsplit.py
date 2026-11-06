#!/usr/bin/env python3
"""Split ONE frame n (1..45) of the 3 s clip into model sub-segments with the guest LCD dump armed.
Handles 1-frame original segments (seg n+3) and 2-frame ones (frames 23..45, see SEGMAP).
Writes OUT/seg<n*100+k>.pkl (k=0..P-1) and OUT/frame<n>.json (per-part console byte counts, instr, tokens).
env: PYTHONPATH=<qwenputer riscv>:<tools dir>"""
import argparse, json, pickle, sys
from pathlib import Path
from model_doom_qwen import clone, breakpoint_at, oracle_run
from upstream_ref import symbols

# frame -> (original seg, offset within the seg)
SEGMAP = {n: (n + 3, 0) for n in range(1, 23)}
for s, (a, b) in {26: (23, 24), 27: (25, 26), 28: (27, 28), 29: (29, 30), 32: (33, 34), 33: (35, 36), 34: (37, 38), 35: (39, 40),
                  36: (41, 42), 37: (43, 44)}.items():
    SEGMAP[a] = (s, 0); SEGMAP[b] = (s, 1)
SEGMAP[31] = (30, 0); SEGMAP[32] = (31, 0); SEGMAP[45] = (38, 0)


def find_P(start, sy_dump, sy_fr):
    """Armed run from `start` until the frame counter increments, then on to a pc not yet executed since `start`."""
    m = clone(start); m.ram[sy_dump // 4] = 1
    f0 = m.ram[sy_fr // 4]; visited = set(); passed = False; marked = False
    while True:
        visited.add(m.pc)
        m.record()
        if m.halted: raise RuntimeError('halted before P')
        if not passed and m.ram[sy_fr // 4] != f0: passed = True
        # P must lie after the frame's end record and marker bytes (01 'E' x x 02), which the guest prints after q_frames++
        if passed and not marked and len(m.out) >= 5 and m.out[-1] == 2 and m.out[-5] == 1 and m.out[-4] == 69: marked = True
        if marked and m.pc not in visited: break
    return m   # state at P (armed-run state)


def parts(m, a, first_index, tag):
    """The original split loop: m = machine (with its stop ebreak in rom) armed; returns list of part dicts."""
    tot, _, _ = oracle_run(clone(m)); total = tot - 1
    print(f'{tag}: {total} instr with dump armed', flush=True)
    res, done, base = [], 0, m.steps
    for k in range(a.parts):
        start = clone(m); s0 = m.steps
        if k == a.parts - 1:
            stop_pc = None
        else:
            target = base + (k + 1) * total // a.parts; visited = set()
            while m.steps < target or m.pc in visited:
                visited.add(m.pc); m.record()
                if m.halted: raise RuntimeError('halted before split')
            stop_pc = m.pc; breakpoint_at(start, stop_pc)
        i, t, out = oracle_run(clone(start)); instr = i - 1
        if stop_pc is not None: assert m.steps - s0 == instr, (m.steps - s0, instr)
        else:
            while not m.halted and m.steps - s0 < instr: m.record()
        res.append(dict(index=first_index + k, start=start, start_steps=s0, stop_pc=stop_pc, instr=instr, tokens=t, out=out,
                        reason='split', rom_chunk=None, markers=0))
        done += instr
        print(f'  part {k}: {instr} instr, {t} tokens, {len(out)} console bytes', flush=True)
    assert done == total, (done, total)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frame', type=int, required=True); ap.add_argument('--snaps', required=True)
    ap.add_argument('--sym-elf', required=True); ap.add_argument('--out', required=True); ap.add_argument('--parts', type=int, default=6)
    a = ap.parse_args()
    sy = symbols(a.sym_elf); dreq, fr = sy['q_dump_req'], sy['q_frames']
    s, off = SEGMAP[a.frame]
    two = s in (26, 27, 28, 29, 32, 33, 34, 35, 36, 37)
    sg = pickle.loads((Path(a.snaps) / f'seg{s}.pkl').read_bytes())
    start = sg['start']
    if not two:
        m = clone(start); m.ram[dreq // 4] = 1
    else:
        P = find_P(start, dreq, fr)
        if off == 0:
            m = clone(start); m.ram[dreq // 4] = 1; breakpoint_at(m, P.pc)
        else:
            m = clone(P); m.ram[dreq // 4] = 1
    res = parts(m, a, a.frame * 100, f'frame {a.frame} (seg {s}, off {off})')
    outd = Path(a.out); outd.mkdir(parents=True, exist_ok=True)
    for d in res: (outd / f'seg{d["index"]}.pkl').write_bytes(pickle.dumps(d, protocol=5))
    (outd / f'frame{a.frame}.json').write_text(json.dumps(dict(frame=a.frame, seg=s, off=off, lens=[len(d['out']) for d in res],
        instr=[d['instr'] for d in res], tokens=[d['tokens'] for d in res], first=a.frame * 100, n=len(res))))


if __name__ == '__main__':
    main()
