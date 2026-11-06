#!/usr/bin/env python3
"""Scripted key-sequence harness for /bin/doomd on tools/rv32_fast (host = keystrokes + dumb disk bytes).
Scenario lines (frame counter advances by the given number of frames):
  hold KEY N     inject KEY on N consecutive frames (held)     tap KEY   = hold KEY 3 then wait 3
  wait N         idle frames
  dump [TAG]     serial frame dump -> PNG named TAG (next frame)
  state          print guest STATE line (needs the test keys)
usage: doomd_play.py IMG SCENARIO PREFIX [--elf E] [--wad W] [--disk-out F]
Keys: w s a d (fwd back turn), q r strafe, space fire, e use, esc, ent, y n, . , tab, z run, x exit level,
g god, i give all, ` state."""
import subprocess, sys, re, os, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)

def compile_scenario(text):
    text = re.sub(r'\bspace\b', 'sp', text)
    f = 2; lines = []; dumps = []
    for ln in text.splitlines():
        ln = ln.split('#')[0].split()
        if not ln: continue
        c = ln[0]
        if c == 'wait': f += int(ln[1])
        elif c == 'hold': lines.append(f"{f}-{f+int(ln[2])-1} {ln[1]}"); f += int(ln[2])
        elif c == 'tap': lines.append(f"{f}-{f+1} {ln[1]}"); f += 20
        elif c == 'dump': lines.append(f"{f} p"); dumps.append(ln[1] if len(ln) > 1 else f"f{f}"); f += 4
        elif c == 'state': lines.append(f"{f} `"); f += 2
        else: raise SystemExit("bad line " + str(ln))
    return "\n".join(lines) + "\n", dumps, f + 4

def stream_sounds(d):
    """Sound events (0x03, 0x80|sfx) of the console stream, skipping the 0x01 dump packets."""
    i = 0; out = []
    while i < len(d):
        c = d[i]
        if c == 1 and i + 1 < len(d):
            t = chr(d[i + 1]); i += 2
            if t == 'P': i += 1
            elif t == 'W': i += 10
            elif t == 'E': i += 2
            elif t == 'D': n = d[i] | d[i + 1] << 8; i += 2 + n
        elif c == 3 and i + 1 < len(d): out.append(d[i + 1] & 0x7f); i += 2
        else: i += 1
    return out

def run(img, scen, prefix, elf=None, wad=None, disk_out=None, maxframes=None, quiet=False):
    script, dumps, nf = compile_scenario(open(scen).read() if os.path.exists(scen) else scen)
    sp = prefix + ".keys"; open(sp, "w").write(script)
    cmd = [os.path.join(ROOT, "build/rv32_fast"), elf or os.path.join(ROOT, "build/qwenos-doomdmc.elf"), img, "100", "108",
           prefix + ".bin", "40000000000", "-s", sp, "-F", str(maxframes or nf)]
    if disk_out: cmd += ["-W", disk_out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not quiet: print(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
    raw = open(prefix + ".bin", "rb").read()
    wadp = wad or "/Users/jhome/qwenos-work/wads/freedoom1.wad"
    subprocess.run([sys.executable, os.path.join(HERE, "doomd_frames.py"), prefix + ".bin", wadp, prefix + "-raw"], capture_output=True)
    # rename dumps by tag
    for i, t in enumerate(dumps):
        a = f"{prefix}-raw-{i:02}.png"
        if os.path.exists(a): os.replace(a, f"{prefix}-{t}.png")
    states = re.findall(rb"STATE ([^\n]*)", raw)
    sounds = stream_sounds(raw)
    return [s.decode() for s in states], sounds, raw, r.stderr

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("img"); ap.add_argument("scen"); ap.add_argument("prefix")
    ap.add_argument("--elf"); ap.add_argument("--wad"); ap.add_argument("--disk-out")
    a = ap.parse_args()
    st, snd, raw, err = run(a.img, a.scen, a.prefix, a.elf, a.wad, a.disk_out)
    for s in st: print("STATE", s)
    print("sounds", snd)
    if b"PANIC" in raw: print("PANIC in output")
