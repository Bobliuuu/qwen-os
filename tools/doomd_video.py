#!/usr/bin/env python3
"""Fast decoder of the /bin/doomd serial LCD dump (same packet format as tools/doomd_frames.py, see
ports/doomdmc/qlcd.c) for builds with -DQ_DUMP_ALL (one 0x01'E' end-of-frame per game tic).
Streams every frame (PLAYPAL colours, real palette number per frame) to ffmpeg, optionally writes stills.
usage: doomd_video.py STREAM.bin freedoom1.wad OUT.mp4 [--scale 3] [--fps 35] [--still N ...] [--stills-dir D] [--gif OUT.gif]"""
import argparse, struct, subprocess, sys, os
import numpy as np

def playpal(wad):
    d = open(wad, 'rb').read()
    n, off = struct.unpack_from('<II', d, 4)
    for i in range(n):
        o, s, nm = struct.unpack_from('<II8s', d, off + 16 * i)
        if nm.rstrip(b'\0') == b'PLAYPAL':
            return np.frombuffer(d[o:o + 768 * 14], np.uint8).reshape(14, 256, 3)
    raise SystemExit('no PLAYPAL')

def frames(stream, pal):
    d = stream if isinstance(stream, (bytes, bytearray)) else open(stream, 'rb').read()
    i = 0; cur = 0; win = None; col = 0
    canvas = np.zeros((240, 320), np.uint8)
    L = len(d)
    while i < L:
        if d[i] != 1:
            i += 1; continue
        t = d[i + 1]; i += 2
        if t == 0x50:      # 'P'
            cur = d[i]; i += 1
        elif t == 0x57:    # 'W'
            win = struct.unpack_from('<5H', d, i); i += 10; col = win[0]
        elif t == 0x44:    # 'D'
            n, = struct.unpack_from('<H', d, i); i += 2
            x0, x1, y0, y1, fl = win; h = y1 - y0 + 1; nc = n // h
            data = np.frombuffer(d, np.uint8, n, i).reshape(nc, h)
            cols = (col - x0 + np.arange(nc)) % (x1 - x0 + 1) + x0
            canvas[y0:y1 + 1, cols] = data.T
            col = int((col - x0 + nc) % (x1 - x0 + 1) + x0)
            i += n
        elif t == 0x45:    # 'E'
            i += 2
            yield pal[cur][canvas]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stream'); ap.add_argument('wad'); ap.add_argument('out')
    ap.add_argument('--scale', type=int, default=3); ap.add_argument('--fps', type=int, default=35)
    ap.add_argument('--still', type=int, nargs='*', default=[]); ap.add_argument('--stills-dir', default='.')
    ap.add_argument('--first', type=int, default=0, help='skip frames before this one')
    a = ap.parse_args()
    pal = playpal(a.wad)
    W, H = 320 * a.scale, 240 * a.scale
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '320x240',
                           '-r', str(a.fps), '-i', '-', '-vf', f'scale={W}:{H}:flags=neighbor', '-c:v', 'libx264',
                           '-preset', 'slow', '-crf', '27', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', a.out],
                          stdin=subprocess.PIPE)
    n = 0
    from PIL import Image
    for k, fr in enumerate(frames(a.stream, pal)):
        if k < a.first: continue
        if k in a.still:
            Image.fromarray(fr).resize((W, H), Image.NEAREST).save(os.path.join(a.stills_dir, f'still-{k:04}.png'))
        ff.stdin.write(fr.tobytes()); n += 1
    ff.stdin.close(); ff.wait()
    print(n, 'frames ->', a.out)

main()
