#!/usr/bin/env python3
"""Per-tic game-state hashes and per-frame picture hashes from a doomd console dump.

  doomd_hashes.py OUT.bin STATES.txt FRAMES.txt

OUT.bin is the console stream rv32_fast wrote for a regression ELF (QHASH=1 + Q_DUMP_ALL, see
tools/doomd_regress.sh).  It carries
  * "TICHASH <gametic> <16 hex>"   lockstep state hash after every game tic (players, sectors, every
    live mobj; tests/lockstep/hash.c of DMC100, rndindex left out): optimisation independent.
  * the full 320x240 pump stream of every frame (0x01 'P'/'W'/'D'/'E' packets, see qlcd.c) and the
    "DOOMD_FRAME n tic t" marker after it.
STATES.txt: one "<tic> <hash>" line per tic.  FRAMES.txt: one "<tic> <md5-12>" line per frame whose
picture (canvas + palette number) differs from the previous frame (a skipped redraw and a repeated
identical redraw are the same thing); tic is the game tic the frame was drawn after.
"""
import hashlib, re, sys


def frames(d):
    """[(tic, md5)] per 'E' packet, tic from the DOOMD_FRAME line printed after the frame."""
    marks = [(m.start(), int(m.group(1))) for m in re.finditer(rb'DOOMD_FRAME \d+ tic (\d+)', d)]
    out, i, mi = [], 0, 0
    cur, win, col, L = 0, None, 0, len(d)
    canvas = bytearray(320 * 240)
    pend = []  # frames whose tic is not yet known
    while i < L:
        if d[i] != 1:
            i += 1
            continue
        t = d[i + 1]
        i += 2
        if t == 80:
            cur = d[i]; i += 1
        elif t == 87:
            win = tuple(d[i + 2 * k] | d[i + 2 * k + 1] << 8 for k in range(5)); i += 10; col = win[0]
        elif t == 68:
            nb = d[i] | d[i + 1] << 8; i += 2
            if i + nb > L:
                break
            x0, x1, y0, y1, _ = win
            h = y1 - y0 + 1
            for c in range(nb // h):
                canvas[y0 * 320 + col:(y1 + 1) * 320 + col:320] = d[i + c * h:i + c * h + h]
                col += 1
                if col > x1:
                    col = x0
            i += nb
        elif t == 69:
            i += 2
            while mi < len(marks) and marks[mi][0] < i:
                mi += 1
            tic = marks[mi][1] if mi < len(marks) else -1
            out.append((tic, hashlib.md5(bytes([cur]) + bytes(canvas)).hexdigest()[:12]))
    return out


def dedupe(fr):
    o = []
    for tic, h in fr:
        if not o or o[-1][1] != h:
            o.append((tic, h))
    return o


def main():
    d = open(sys.argv[1], 'rb').read()
    st = [(int(a), b) for a, b in re.findall(r'TICHASH (\d+) ([0-9a-f]{16})', d.decode('latin1'))]
    fr = dedupe(frames(d))
    open(sys.argv[2], 'w').write(''.join(f'{a} {b}\n' for a, b in st))
    open(sys.argv[3], 'w').write(''.join(f'{a} {b}\n' for a, b in fr))
    print(f'{len(st)} tic hashes, {len(fr)} distinct-consecutive frames')


if __name__ == '__main__':
    main()
