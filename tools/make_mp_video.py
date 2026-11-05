#!/usr/bin/env python3
"""v2 clip made ONLY from model-decoded frames: title card, a real-time pass (15 fps, the clip's own rate), then a slow pass (3 fps).
  make_mp_video.py FRAMES_DIR OUT_BASENAME FRAME[,FRAME..]     (frame_NN_model.png, rows 0-199 = the view the dump carries)"""
import subprocess, sys, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

d, out, fl = Path(sys.argv[1]), sys.argv[2], [int(x) for x in sys.argv[3].split(',')]
S = 3; W, H = 320 * S, 200 * S
try: font = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 30); small = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 22)
except Exception: font = small = ImageFont.load_default()
card = Image.new('RGB', (W, H), (16, 16, 24)); g = ImageDraw.Draw(card)
lines = ['QwenOS DOOM, v2: model-decoded pixels', '', 'pixels emitted by the Qwen model as console', 'byte tokens, lockstep-verified,', f'{len(fl)} frames (E1M1 clip frames {fl[0]}-{fl[-1]}).', '',
         'view rows 0-199 only; status bar not in dump.', 'pass 1: real time (15 fps). pass 2: slow (3 fps).']
for i, t in enumerate(lines): g.text((40, 60 + 40 * i), t, fill=(240, 240, 240), font=font if i == 0 else small)
tmp = Path(tempfile.mkdtemp(prefix='mpv'))
seq = []
def add(img, n):
    seq.extend([img] * n)
add(card, 45)
imgs = [Image.open(d / f'frame_{f:02d}_model.png').convert('RGB').crop((0, 0, 320, 200)).resize((W, H), Image.NEAREST) for f in fl]
for im in imgs: add(im, 2)          # 30 fps timeline: 2 ticks = 15 fps
add(card.copy(), 15)
for im in imgs: add(im, 10)         # 3 fps
for i, im in enumerate(seq): im.save(tmp / f'{i:05d}.png')
subprocess.check_call(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '30', '-i', str(tmp / '%05d.png'), '-pix_fmt', 'yuv420p', '-c:v', 'libx264', '-crf', '18', out + '.mp4'])
subprocess.check_call(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '30', '-i', str(tmp / '%05d.png'), '-vf', 'fps=10,scale=480:-1:flags=neighbor,split[a][b];[a]palettegen[p];[b][p]paletteuse', out + '.gif'])
print('wrote', out + '.mp4', out + '.gif')
