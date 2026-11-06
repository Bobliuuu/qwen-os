#!/usr/bin/env python3
"""fpdecode.py N : fetch results of frame N (modal volume qwenos-results fp45/fN), check model result, decode model bytes, compare with emulator.
Writes work/final/frame_NN_model.png, model_stream_NN.bin, verdict_NN.json (never overwrites a verdict of another frame)."""
import json, subprocess, sys, types
from pathlib import Path
W = Path('/Users/jhome/qwenos-work/out/clip_modelpixels/work')
TOOLS = '/Users/jhome/qwenos-work/publish/qwen-os/.claude/worktrees/agent-afe6f4cb6ddd829a7/tools'
sys.path.insert(0, TOOLS)
import model_fbdump as F

n = int(sys.argv[1]); TAG = sys.argv[2] if len(sys.argv) > 2 else 'fp45'
res = W / 'res' / f'f{n}'; res.mkdir(parents=True, exist_ok=True)
subprocess.run(['modal', 'volume', 'get', 'qwenos-results', f'{TAG}/f{n}', str(W / 'res'), '--force'], check=True, stdout=subprocess.DEVNULL)
r = json.loads((res / 'result.json').read_text())
meta = json.loads((W / 'snaps' / f'frame{n}.json').read_text())
sd = r.get('segment_detail') or []
ok = (r.get('mode') == 'MODEL' and len(sd) == meta['n'] and all(x[1] for x in sd)
      and [x[3] for x in sd] == meta['instr'] and [x[4] for x in sd] == meta['tokens'])
mb = res / 'console.bin.model'
verdict = dict(frame=n, model_run_ok=bool(ok), mode=r.get('mode'), segs=len(sd), wall=r.get('wall_seconds'), instr=sum(meta['instr']),
               tokens=sum(meta['tokens']), gpu=r.get('gpu') or r.get('device'))
if not mb.exists() or mb.stat().st_size != sum(meta['lens']):
    verdict.update(exact=False, why=f'model bytes {mb.stat().st_size if mb.exists() else None} != {sum(meta["lens"])}')
else:
    out = W / 'final'; out.mkdir(exist_ok=True)
    a = types.SimpleNamespace(model_bytes=[str(mb)], frames=str(n), frame_lengths=str(sum(meta['lens'])),
                              wad='/Users/jhome/qwenos-work/wads/freedoom1.wad', emu_frames='/Users/jhome/qwenos-work/out/clip/frames', out=str(out))
    tab = F.decode(a)[0]
    chunk = mb.read_bytes(); cov = F.painted_rows(chunk)
    full200 = all(y in cov for y in range(200))
    pr, rr = F.png_rows(out / f'frame_{n:02d}_model.png'), F.png_rows(Path(a.emu_frames) / f'frame_{n:02d}.png')
    bad200 = [y for y in range(200) if pr[y] != rr[y]]
    verdict.update(model_bytes=tab[1], painted_rows=tab[2], bad_painted=tab[3], bad_rows_0_199=len(bad200), rows_0_199_painted=full200,
                   exact=bool(ok and full200 and not bad200), md5=tab[6])
(W / 'final').mkdir(exist_ok=True)
(W / 'final' / f'verdict_{n:02d}.json').write_text(json.dumps(verdict))
print(json.dumps(verdict))
