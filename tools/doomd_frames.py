#!/usr/bin/env python3
"""Decode the /bin/doomd serial LCD dump (see ports/doomdmc/qlcd.c) from the console byte
stream written by tools/rv32_fast.c into 320x240 PNGs. Palette: PLAYPAL of the IWAD."""
import struct, sys, zlib
from pathlib import Path

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
    stream, wad, prefix = sys.argv[1:4]
    scale = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    pal = playpal(wad)
    d = Path(stream).read_bytes()
    i = 0; cur = 0; win = None; col = 0
    canvas = bytearray(320 * 240)
    nframes = 0
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
            for c in range(n // h):
                for y in range(h):
                    canvas[(y0 + y) * 320 + col] = d[i + c * h + y]
                col += 1
                if col > x1: col = x0
            i += n
        elif t == 'E':
            i += 2
            rgb = bytearray()
            for p in canvas: rgb += bytes(pal[cur][p])
            if scale > 1:
                big = bytearray()
                for y in range(240):
                    row = b''.join(bytes(rgb[(y * 320 + x) * 3:(y * 320 + x) * 3 + 3]) * scale for x in range(320))
                    big += row * scale
                png(f'{prefix}-{nframes:02}.png', 320 * scale, 240 * scale, big)
            else:
                png(f'{prefix}-{nframes:02}.png', 320, 240, rgb)
            nframes += 1
    print(nframes, 'frames')
main()
