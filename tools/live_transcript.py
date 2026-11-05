#!/usr/bin/env python3
"""Run the live QwenOS terminal (tools/qwenos_live.sh --auto) in a pseudo-terminal like a human at a keyboard and
print a plain-text transcript: shell output, then the first DOOM frames as ASCII art (decoded from the ANSI the
host display emits), then quit with Ctrl-].   usage: tools/live_transcript.py [frames=3] [extra qwenos_live.sh args]
Tier T0 (host emulator). Used for docs/LIVE_DEMO.md; tests/test_live.py covers the same flow."""
import fcntl, os, pty, re, select, struct, subprocess, sys, termios, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
RAMP = " .:-=+*#%@"

def run(nframes=3, extra=(), timeout=300):
    m, s = pty.openpty()
    fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 100, 0, 0))
    p = subprocess.Popen([str(ROOT / 'tools/qwenos_live.sh'), '--auto', '--fps', '0', *extra], stdin=s, stdout=s, stderr=s, close_fds=True)
    os.close(s); buf = b''; end = time.time() + timeout
    while time.time() < end and p.poll() is None:
        r, _, _ = select.select([m], [], [], 0.2)
        if r:
            try: d = os.read(m, 65536)
            except OSError: break
            if not d: break
            buf += d
        if len(re.findall(rb'frame (\d+) \|', buf)) and max(int(x) for x in re.findall(rb'frame (\d+) \|', buf)) >= nframes + 1: break
    os.write(m, b'\x1d')
    t = time.time() + 20
    while time.time() < t and p.poll() is None:
        r, _, _ = select.select([m], [], [], 0.2)
        if r:
            try: buf += os.read(m, 65536)
            except OSError: break
    return buf

def lum(rgb): return (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000

def frames_ascii(buf):
    """split the ANSI stream at cursor-home, decode each screen of half-block cells into ASCII (2 rows per cell row)"""
    i = buf.find(b'\x1b[?1049h'); out = []
    if i < 0: return out
    for scr in re.split(rb'\x1b\[H', buf[i:])[1:]:
        rows = []; cur = None
        for line in scr.split(b'\r\n'):
            top = []; bot = []; half = False
            for m in re.finditer(rb'\x1b\[(?:38;2;(\d+);(\d+);(\d+);)?48;2;(\d+);(\d+);(\d+)m((?:\xe2\x96\x80| )+)', line):
                bg = tuple(int(x) for x in m.group(4, 5, 6)); n = len(m.group(7).replace(b'\xe2\x96\x80', b'.'))
                if m.group(1): half = True; fg = tuple(int(x) for x in m.group(1, 2, 3))
                else: fg = bg
                top.append(RAMP[min(9, int(lum(fg) / 25.6))] * n); bot.append(RAMP[min(9, int(lum(bg) / 25.6))] * n)
            if top: rows += [''.join(top), ''.join(bot)] if half else [''.join(bot)]
        if rows: out.append(rows)
    return out

if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    buf = run(n, sys.argv[2:])
    text = buf[:buf.find(b'\x1b[?1049h')] if b'\x1b[?1049h' in buf else buf
    print(text.decode('utf8', 'replace').replace('\r\n', '\n'))
    fr = frames_ascii(buf)
    status = re.findall(rb'guest instr (\d+) \| frame (\d+) \| ([\d.]+) fps', buf)
    for k, rows in enumerate(fr[:n]):
        print('--- DOOM frame %d (%d x %d ASCII, decoded from the display ANSI) ---' % (k, len(rows[0]), len(rows)))
        print('\n'.join(rows))
    if status: print('status line at end: guest instr %s | frame %s' % tuple(x.decode() for x in status[-1][:2]))
    m = re.search(rb'QwenOS live: [^\r\n]*', buf)
    if m: print(m.group(0).decode())
    sys.exit(0 if fr else 1)
