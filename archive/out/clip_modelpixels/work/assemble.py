#!/usr/bin/env python3
"""Concatenate the model-emitted dump streams of frames 1..45 in order, decode with the framebuffer carried across frames, compare
with the emulator frames (all 240 rows and rows 0-199). Writes final/seq_NN.png (decoded frames) and final/assemble.json."""
import json, subprocess, sys
from pathlib import Path
W = Path('/Users/jhome/qwenos-work/out/clip_modelpixels/work'); C = W.parent
sys.path.insert(0, '/Users/jhome/qwenos-work/publish/qwen-os/.claude/worktrees/agent-afe6f4cb6ddd829a7/tools')
import model_fbdump as F
buf, lens = b'', []
for n in range(1, 46):
    p = C / f'model_stream_{n:02d}.bin' if 12 <= n <= 19 else W / 'res' / f'f{n}' / 'console.bin.model'
    if 12 <= n <= 19 and not p.exists(): p = C / f'model_stream_{n}.bin'
    d = p.read_bytes(); buf += d; lens.append(len(d))
out = W / 'final'; (out / 'seq').mkdir(parents=True, exist_ok=True)
(out / 'model_stream_all.bin').write_bytes(buf)
subprocess.check_call([sys.executable, '/Users/jhome/qwenos-work/publish/qwen-os/.claude/worktrees/agent-afe6f4cb6ddd829a7/tools/lowres_frames.py',
                       str(out / 'model_stream_all.bin'), '/Users/jhome/qwenos-work/wads/freedoom1.wad', str(out / 'seq' / 'f'), '1', 'all'], stdout=subprocess.DEVNULL)
res = []
for n in range(1, 46):
    pr = F.png_rows(out / 'seq' / f'f-{n-1:03d}.png'); rr = F.png_rows(Path('/Users/jhome/qwenos-work/out/clip/frames') / f'frame_{n:02d}.png')
    bad = [y for y in range(240) if pr[y] != rr[y]]; bad200 = [y for y in bad if y < 200]
    res.append(dict(frame=n, bytes=lens[n - 1], bad_rows_0_239=len(bad), bad_rows_0_199=len(bad200), exact200=not bad200, exact240=not bad))
(out / 'assemble.json').write_text(json.dumps(res))
print(sum(r['exact200'] for r in res), '/45 exact rows 0-199;', sum(r['exact240'] for r in res), '/45 exact rows 0-239')
for r in res:
    if not r['exact240']: print(r)
