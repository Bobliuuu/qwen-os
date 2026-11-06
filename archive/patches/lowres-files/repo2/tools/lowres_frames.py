#!/usr/bin/env python3
"""Decode the /bin/doomd serial LCD dump of the lowres builds (qlcd.c; window flags bit0 = columns
doubled, bit1 = columns x4, bit8 = compact dump: the host repeats every column) into PNGs.
  lowres_frames.py out.bin freedoom1.wad prefix SCALE IDX[,IDX..]   (IDX = frame numbers, 'all' = every frame)
Palette: PLAYPAL of the IWAD. Output is the 320x240 picture, nearest-neighbour upscaled by SCALE."""
import struct, sys, zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

def playpal(wad):
    d = Path(wad).read_bytes()
    n, off = struct.unpack_from('<II', d, 4)
    for i in range(n):
        o, s, nm = struct.unpack_from('<II8s', d, off + 16 * i)
        if nm.rstrip(b'\0') == b'PLAYPAL':
            return [[tuple(d[o + 768 * p + 3 * i: o + 768 * p + 3 * i + 3]) for i in range(256)] for p in range(14)]
    raise SystemExit('no PLAYPAL')

def png(path, w, h, rgb):
    raw = b''.join(b'\0' + bytes(rgb[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    def ch(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d))
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw)) + ch(b'IEND', b''))

def main():
    stream, wad, prefix, scale, sel = sys.argv[1:6]
    scale = int(scale)
    want = None if sel == 'all' else set(int(x) for x in sel.split(','))
    pal = playpal(wad)
    d = Path(stream).read_bytes()
    i = 0; cur = 0; win = None; col = 0
    canvas = bytearray(320 * 240)
    nf = 0
    while i < len(d):
        if d[i] != 1:
            i += 1; continue
        t = chr(d[i + 1]); i += 2
        if t == 'P':
            cur = d[i]; i += 1
        elif t == 'W':
            win = struct.unpack_from('<5H', d, i); i += 10; col = win[0]
        elif t == 'D':
            n, = struct.unpack_from('<H', d, i); i += 2
            x0, x1, y0, y1, fl = win; h = y1 - y0 + 1
            rep = 1
            if fl & 0x100:
                rep = 4 if fl & 2 else 2 if fl & 1 else 1
            hs = (h + 1) // 2 if fl & 4 else h
            for c in range(n // hs):
                column = d[i + c * hs:i + c * hs + hs]
                if hs != h:
                    column = bytes(column[y >> 1] for y in range(h))
                for _ in range(rep):
                    canvas[y0 * 320 + col:(y1 + 1) * 320 + col:320] = column
                    col += 1
                    if col > x1: col = x0
            i += n
        elif t == 'E':
            i += 2
            if want is None or nf in want:
                rgb = bytearray()
                p = pal[cur]
                for px in canvas: rgb += bytes(p[px])
                if scale > 1:
                    big = bytearray()
                    for y in range(240):
                        row = b''.join(bytes(rgb[(y * 320 + x) * 3:(y * 320 + x) * 3 + 3]) * scale for x in range(320))
                        big += row * scale
                    png(f'{prefix}-{nf:03}.png', 320 * scale, 240 * scale, big)
                else:
                    png(f'{prefix}-{nf:03}.png', 320, 240, rgb)
            nf += 1
    print(nf, 'frames')
main()
