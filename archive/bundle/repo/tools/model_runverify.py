#!/usr/bin/env python3
"""Merge/verify the parallel chunk-ROM model run and print PROVENANCE.md ledger rows.

  tools/model_runverify.py --runplan out/model/p45/runplan.json --results out/model/chunks [--label clip3s] [--append PROVENANCE.md]
Each chunk dir ~/out/<cNN>/result.json is the --result-json of one model_doom_qwen.py chunk (fleet runner layout).
PASS = every chunk is MODEL mode, ran exactly its segment range, every segment ok (host==model console bytes, instr count
equal, lockstep zero divergence), chunk markers add up to --frames, chunk ranges are contiguous from marker 0, and
the sum of planned instructions equals the plan. Prints 'COVERED frames 1..F' only if all hold.
"""
import argparse, json, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--runplan', required=True); ap.add_argument('--results', required=True)
ap.add_argument('--label', default='clip'); ap.add_argument('--logdir', default='out/model/chunks')
ap.add_argument('--append', default=None)
a = ap.parse_args()
plan = json.loads(Path(a.runplan).read_text())
rows, bad, seen_markers, tok, secs = [], [], 0, 0, 0
nxt = 0
for c in plan['chunks']:
    f = Path(a.results) / f"c{c['chunk']:02d}" / 'result.json'
    A, B = (int(x) for x in c['segment_range'].split(':'))
    if c['marker_start'] != nxt:
        bad.append(f"chunk {c['chunk']} starts at marker {c['marker_start']}, expected {nxt}")
    nxt = c['marker_end']
    if not f.exists():
        bad.append(f"chunk {c['chunk']}: no result"); rows.append(f"| {a.label}/{c['chunk']} | - | markers {c['marker_start']} | markers {c['marker_end']} | {c['frames']} | - | - | N (not run) | - | - |"); continue
    r = json.loads(f.read_text())
    ok = (r['mode'] == 'MODEL' and r['segments'] == B - A and r['first_segment'] == A
          and all(d[1] for d in r['segment_detail']) and r.get('frame_markers_in_output', 0) == c['frames']
          and r.get('instructions') == c['instr'])
    if not ok: bad.append(f"chunk {c['chunk']}: failed ({r['mode']}, segments {r['segments']}/{B-A}, markers {r.get('frame_markers_in_output')}/{c['frames']})")
    seen_markers += r.get('frame_markers_in_output', 0); tok += r['model_chip_tokens']; secs = max(secs, r['wall_seconds'])
    rows.append(f"| {a.label}/{c['chunk']} | {r['gpu']} ({r['host']}, executor={r['executor']}) | segs {c['segment_range']}, "
                f"frame-markers before {c['marker_start']}, chunk ROM {c['rom_chunk_at_start']} | frame-markers {c['marker_end']} | {c['frames']} | "
                f"{r['model_chip_tokens']} chip + {r['model_text_tokens']} text ({r['chip_tokens_per_s']} chip tok/s, {r['instr_per_s']} instr/s) | "
                f"{r['wall_seconds']} s | {'Y' if ok else 'N'} | {'none' if ok else 'see log'} | {a.logdir}/c{c['chunk']:02d}/result.json |")
if nxt != plan['frames']: bad.append(f'plan ends at marker {nxt}, not {plan["frames"]}')
if seen_markers != plan['frames']: bad.append(f'verified markers {seen_markers} != {plan["frames"]}')
print('\n'.join(rows))
if a.append:
    p = Path(a.append)
    head = '' if '## 5. Auto-appended' in p.read_text() else ('\n## 5. Auto-appended chunk rows (model_doom_chunks.py ledger)\n\n| Chunk | GPU/box | Start | End | Frames emitted | Tokens | Wall | Verified | Divergence | Log |\n|---|---|---|---|---|---|---|---|---|---|\n')
    with p.open('a') as fh: fh.write(head + '\n'.join(rows) + f"\n<!-- run {a.label}: {seen_markers} frames, {tok} chip tokens, slowest chunk {secs} s -->\n")
if bad:
    print('FAIL:'); [print(' ', b) for b in bad]; sys.exit(1)
print(f"COVERED frames 1..{plan['frames']}: {len(plan['chunks'])} chunks, {tok} chip tokens verified, slowest chunk {secs:.0f} s")
