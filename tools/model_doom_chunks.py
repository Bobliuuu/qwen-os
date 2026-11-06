#!/usr/bin/env python3
"""Split a model_doom_qwen.py target into N token-balanced chunks and merge per-chunk results.

  plan:   model_doom_chunks.py plan  --n 4 [model_doom_qwen.py args: --elf --disk --target ...] --out-dir D
          (host-only pass; writes D/plan.json and D/chunks.json with segment ranges A:B and token counts,
           and D/run_chunk_<i>.sh lines in D/commands.txt)
  merge:  model_doom_chunks.py merge --out-dir D   -> D/report.json; proves every segment 1..S is covered
          exactly once, no divergence, and sums instructions/tokens/bytes/wall (max over chunks).
Chunks are independent: each starts from a reference-machine snapshot, so they can run on different GPUs.
"""
import argparse, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['plan', 'merge'])
    ap.add_argument('--n', type=int, default=2)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--model', default='MODEL_DIR')
    a, rest = ap.parse_known_args()
    d = Path(a.out_dir); d.mkdir(parents=True, exist_ok=True)
    if a.cmd == 'plan':
        subprocess.check_call([sys.executable, str(HERE / 'model_doom_qwen.py'), '--dry-run', '--plan-json',
                               str(d / 'plan.json')] + rest)
        segs = json.loads((d / 'plan.json').read_text())
        total = sum(s['tokens'] + s['out'] * 40 for s in segs)  # a console byte costs ~ a full text token
        chunks, cur, acc, i0 = [], 0, 0, 1
        for s in segs:
            acc += s['tokens'] + s['out'] * 40
            if acc >= total * (len(chunks) + 1) / a.n and len(chunks) < a.n - 1:
                chunks.append((i0, s['index'] + 1)); i0 = s['index'] + 1
        chunks.append((i0, len(segs) + 1))
        info = [dict(chunk=i, range=f'{x}:{y}', segments=y - x,
                     instr=sum(s['instr'] for s in segs[x - 1:y - 1]),
                     tokens=sum(s['tokens'] for s in segs[x - 1:y - 1])) for i, (x, y) in enumerate(chunks)]
        (d / 'chunks.json').write_text(json.dumps(info, indent=2))
        cmds = [f"python tools/model_doom_qwen.py {a.model} {' '.join(rest)} --segment-range {c['range']} "
                f"--out {d}/chunk{c['chunk']}.bin --result-json {d}/chunk{c['chunk']}.json" for c in info]
        (d / 'commands.txt').write_text('\n'.join(cmds) + '\n')
        print(json.dumps(info, indent=2))
    else:
        segs = json.loads((d / 'plan.json').read_text())
        info = json.loads((d / 'chunks.json').read_text())
        res, missing = [], []
        for c in info:
            f = d / f"chunk{c['chunk']}.json"
            if f.exists():
                res.append(json.loads(f.read_text()))
            else:
                missing.append(c['chunk'])
        covered = sorted((int(r['segment_range'].split(':')[0]), int(r['segment_range'].split(':')[1])) for r in res)
        pos, gaps = 1, []
        for x, y in covered:
            if x != pos: gaps.append((pos, x))
            pos = y
        if pos != len(segs) + 1: gaps.append((pos, len(segs) + 1))
        rep = dict(chunks_done=len(res), chunks_missing=missing, coverage_gaps=gaps,
                   complete=not missing and not gaps and all(r['mode'] == 'MODEL' for r in res),
                   segments=sum(r['segments'] for r in res), planned_segments=len(segs),
                   instructions=sum(r['instructions'] for r in res), planned_instructions=sum(s['instr'] for s in segs),
                   model_chip_tokens=sum(r['model_chip_tokens'] for r in res),
                   planned_chip_tokens=sum(r['planned_chip_tokens'] for r in res),
                   model_text_tokens=sum(r['model_text_tokens'] for r in res),
                   console_bytes=sum(r['console_bytes'] for r in res),
                   frame_markers=sum(r['frame_markers_in_output'] for r in res),
                   wall_seconds_max=max([r['wall_seconds'] for r in res] or [0]),
                   wall_seconds_sum=sum(r['wall_seconds'] for r in res),
                   note='a chunk exits nonzero without a result json on any divergence/consistency failure')
        (d / 'report.json').write_text(json.dumps(rep, indent=2)); print(json.dumps(rep, indent=2))


if __name__ == '__main__':
    main()
