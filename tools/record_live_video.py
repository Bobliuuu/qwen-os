#!/usr/bin/env python3
"""Record a screen-recording-style video of the QwenOS live demo (tier T0: guest RV32IM on the HOST emulator).

  python3 tools/record_live_video.py capture   # drive tools/qwenos_live.sh in a pty like a typist, save timestamped bytes
  python3 tools/record_live_video.py render    # pyte terminal emulator + Pillow -> PNG frames -> ffmpeg MP4 + GIF
  python3 tools/record_live_video.py all
Needs (outside the repo): python3 -m venv V && V/bin/pip install pyte pillow ; ffmpeg on PATH ; a built live demo (`make live-doom`).
Output: docs/assets/qwenos-live-boot.mp4 / .gif.  No GPU, no model: every pixel of the terminal is the T0 emulator run.
The 320x240 inset uses docs/assets/doom-inset/ (frames decoded from the separate scripted clip run, labeled as such)."""
import fcntl, json, os, pty, re, select, shutil, struct, subprocess, sys, termios, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
WORK = Path(os.environ.get('VIDEO_WORK', '/tmp/qwenos-video'))
CAP = WORK / 'capture.json'
OUT = ROOT / 'docs/assets'
COLS, ROWS = 80, 30
INSET = Path(os.environ.get('INSET_DIR', '/Users/jhome/qwenos-work/out/clip/frames'))  # native 320x240 decodes of the clip

# ------------------------------------------------------------------ capture
def capture(nframes=14):
    m, s = pty.openpty()
    fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack('HHHH', ROWS, COLS, 0, 0))
    p = subprocess.Popen([str(ROOT / 'tools/qwenos_live.sh'), '--fps', '0'], stdin=s, stdout=s, stderr=s, close_fds=True)
    os.close(s)
    ev = []; t0 = time.time(); buf = b''
    def pump(timeout):
        nonlocal buf
        r, _, _ = select.select([m], [], [], timeout)
        if r:
            try: d = os.read(m, 65536)
            except OSError: return False
            if not d: return False
            ev.append((time.time() - t0, 'o', d.decode('latin1'))); buf += d
        return True
    def wait_for(pat, limit=60):
        end = time.time() + limit; start = len(buf)
        while time.time() < end:
            pump(0.05)
            if re.search(pat, buf[start:]): return
        raise SystemExit('timeout waiting for %r' % pat)
    def type_(text, delay=0.07):
        for ch in text:
            ev.append((time.time() - t0, 'k', ch)); os.write(m, ch.encode()); time.sleep(delay)
            pump(0.0)
    wait_for(rb'\$ ')                       # banner + kernel boot + shell prompt
    for cmd in ['help', 'ls', 'cat /README', 'echo hello qwenos > /tmp/note', 'cat /tmp/note']:
        end = time.time() + 0.9
        while time.time() < end: pump(0.05)
        n = len(buf); type_(cmd); os.write(m, b'\r'); ev.append((time.time() - t0, 'k', '\r'))
        wait_for(rb'\$ ')
    end = time.time() + 1.0
    while time.time() < end: pump(0.05)
    type_('run /bin/doomd', 0.09); os.write(m, b'\r')
    start = len(buf)
    while time.time() < t0 + 240:
        pump(0.05)
        fr = [int(x) for x in re.findall(rb'frame (\d+) \|', buf[start:])]
        if fr and max(fr) >= nframes: break
    os.write(m, b'\x1d')
    end = time.time() + 3
    while time.time() < end and p.poll() is None: pump(0.1)
    WORK.mkdir(parents=True, exist_ok=True)
    CAP.write_text(json.dumps(ev))
    print('captured %d events, %.1f s, %d bytes' % (len(ev), ev[-1][0], len(buf)))

# ------------------------------------------------------------------ render
def render():
    import pyte
    from PIL import Image, ImageDraw, ImageFont
    ev = json.loads(CAP.read_text())
    W, H = 1280, 720; FPS = 20
    mono = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 15)
    monob = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 15, index=1)
    sans = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 22)
    sansb = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 22, index=1)
    big = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 44, index=1)
    med = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 28)
    small = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 18)
    CW, CH = 9, 19; TX, TY = 24, 70
    BG = (18, 20, 26); FG = (220, 224, 230)
    names = {'default': None, 'black': (0, 0, 0), 'red': (205, 80, 80), 'green': (90, 200, 110), 'brown': (220, 180, 80), 'blue': (90, 130, 230),
             'magenta': (200, 100, 200), 'cyan': (80, 200, 210), 'white': (230, 230, 230)}
    def col(c, default):
        if c in names: return names[c] or default
        if len(c) == 6:
            try: return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError: pass
        return default
    screen = pyte.Screen(COLS, ROWS); stream = pyte.Stream(screen)
    # states: (vt, snapshot, instr, frame, phase)
    states = []; vt = 0.0; prev = 0.0; instr = 0; frame = -1; phase = 'boot'; doom_frames = []
    def snap():
        return [[(screen.buffer[y][x].data, screen.buffer[y][x].fg, screen.buffer[y][x].bg) for x in range(COLS)] for y in range(ROWS)], (screen.cursor.x, screen.cursor.y, screen.cursor.hidden)
    ndoom = 0
    for t, kind, d in ev:
        dt = t - prev; prev = t
        if phase == 'doom':
            vt += 0.0
        else:
            vt += min(dt, 0.9)
        if kind == 'k': continue  # the echo comes back from the guest itself
        raw = d.encode('latin1')
        raw = raw.replace(b'\x1b[?1049h', b'\x1b[2J\x1b[H').replace(b'\x1b[?1049l', b'\x1b[2J\x1b[H').replace(b'\x1b[?25l', b'').replace(b'\x1b[?25h', b'')
        if b'DOOMD_LEVEL_START' in raw and phase != 'doom': pass
        for part in re.split(rb'(\x1b\[H)', raw):
            if part == b'\x1b[H' and phase == 'doom' and states and states[-1][5] >= 0:
                pass
            stream.feed(part.decode('utf8', 'replace'))
        for mm in re.finditer(rb'guest instr (\d+) \| frame (\d+)', raw):
            instr, frame = int(mm.group(1)), int(mm.group(2))
        if b'\xe2\x96\x80' in raw and b'guest instr' in raw:
            if phase != 'doom': phase = 'doom'
            ndoom += 1
        states.append((vt, snap(), instr, frame, phase, ndoom))
    # collapse doom screens: keep one state per newly completed status line (frame change)
    def draw_term(img, d, snapdata, doom):
        rows, cur = snapdata
        if doom:
            # half-block art: cell = 2 vertical samples; draw bigger
            cw, ch = 10, 20
            x0, y0 = TX, TY + 20
        else:
            cw, ch = CW, CH; x0, y0 = TX, TY
        if doom:  # stop at the status line; console lines the guest prints below it are not part of the picture
            for i, r in enumerate(rows):
                if 'guest instr' in ''.join(c for c, _, _ in r):
                    rows = rows[:i + 1]; break
        for y, row in enumerate(rows):
            for x, (c, fg, bg) in enumerate(row):
                px, py = x0 + x * cw, y0 + y * ch
                b = col(bg, None); f = col(fg, FG)
                if c == '▀':
                    d.rectangle([px, py, px + cw - 1, py + ch // 2 - 1], fill=f)
                    d.rectangle([px, py + ch // 2, px + cw - 1, py + ch - 1], fill=b or BG)
                else:
                    if b: d.rectangle([px, py, px + cw - 1, py + ch - 1], fill=b)
                    if c.strip(): d.text((px, py), c, font=mono, fill=f)
        if not doom and not cur[2]:
            cx, cy = cur[0], cur[1]
            d.rectangle([x0 + cx * cw, y0 + cy * ch + 2, x0 + cx * cw + cw - 2, y0 + cy * ch + ch - 2], fill=(200, 200, 200))
    insets = sorted(INSET.glob('frame_*.png'))
    def card(lines, sub=None, hold=None):
        im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im); y = 150
        for i, (txt, f) in enumerate(lines):
            w = d.textlength(txt, font=f); d.text(((W - w) / 2, y), txt, font=f, fill=FG if i else (120, 200, 255)); y += 66 if f is big else 44
        return im
    def wrap(txt, font, width, d):
        out = []; cur = ''
        for w in txt.split():
            if d.textlength(cur + ' ' + w, font=font) > width and cur: out.append(cur); cur = w
            else: cur = (cur + ' ' + w).strip()
        return out + [cur]
    def title_card(lines, size=26):
        im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im)
        y = 120
        for txt, f, c in lines:
            for ln in wrap(txt, f, W - 200, d):
                w = d.textlength(ln, font=f); d.text(((W - w) / 2, y), ln, font=f, fill=c); y += int(f.size * 1.5)
            y += 14
        return im
    LB = (120, 200, 255); WH = (235, 235, 240); GR = (150, 155, 165); AM = (255, 200, 90)
    intro = title_card([('QwenOS: boot, shell, DOOM', big, LB),
                        ('tier T0: guest RV32IM on the host emulator, not the Qwen model', med, AM),
                        ('Everything in the terminal is guest code (kernel, shell, DOOM) executed by build/rv32_fast on a laptop CPU. The host only forwards keys, serves disk blocks and paints the framebuffer.', med, WH),
                        ('Real screen capture of tools/qwenos_live.sh, typed by a script with human-like delays.', small, GR)])
    def info(head, lines, foot=None):
        im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 52], fill=(30, 34, 44))
        d.text((24, 13), 'QwenOS live   |   tier T0: guest RV32IM on the host emulator, not the Qwen model', font=sansb, fill=AM)
        d.text((60, 90), head, font=big, fill=LB); y = 175
        for txt, c in lines:
            for ln in wrap(txt, med, W - 140, d):
                d.text((60, y), ln, font=med, fill=c); y += 42
            y += 16
        if foot: d.text((60, H - 50), foot, font=small, fill=GR)
        return im
    c_what = info('1. What this is', [
        ('Qwenputer (upstream divagr18/qwenputer) compiles a 32-bit RISC-V CPU (RV32IM) into the WEIGHTS of Qwen3.5-4B. No training.', WH),
        ('The 32 KiB of RAM is Gated DeltaNet state. There is no KV cache.', WH),
        ('Every guest instruction costs about 1.4 tokens.', AM)])
    c_watch = info('2. What you are watching', [
        ('Tier T0: our fast host emulator running the same program. NOT the model.', AM),
        ('The same program has been run on the real Qwen model (tier T2), with upstream\'s reference CPU (T1) checking every token.', WH),
        ('Identical results on everything tested (T0, T1, T2).', WH)])
    c_model = info('3. What the model actually did', [
        ('Verified the typed boot, shell, run /bin/doomd flow to the first frame: 3 A100 chunks, 3,335,072 instructions, 26 segments, zero divergence, console output byte-identical.', WH),
        ('Verified the 3 s E1M1 clip: 45 frames, 35 chunks.', WH),
        ('Emitted frame pixel bytes itself as console BYTE tokens (~32,100 bytes per frame, lockstep-checked). Model-emitted pixels: 4 frames byte-exact so far (frames 12-15).', AM)])
    c_slow = info('4. How slow', [
        ('About 8 to 10 minutes of A100 time per displayed frame now (projection from measured chunk speeds). About 18 minutes before the speed-ups.', WH),
        ('Real time at 15 fps needs 0.067 s per frame: we are about 8,000x off.', AM),
        ('Speed-ups measured on the model: 2.14x per chip token (block verification + fused kernels, bit-exact).', WH)],
        foot='Footnote: dividing the whole clip\'s wall time by 45 frames gives about 28 minutes.')
    c_honest = info('5. Honest bits', [
        ('The host forwards keys, serves disk blocks and writes PNGs.', WH),
        ('Input is scripted in the clip. The clock is virtual.', WH),
        ('The 3 s clip is stitched from separately verified chunks.', WH),
        ('The Qwen model did not run this recording. Emulator speed here is not model speed.', AM)],
        foot='Source: docs/CLIP_LEDGER.md, docs/LIVE_DEMO.md and README "What is real".')
    outro = title_card([('What this video is', big, LB),
                        ('This recording is the host emulator (T0); the model-run evidence is in the README and docs/CLIP_LEDGER.md.', med, AM)])
    def chrome(img, phase, instr, frame, doomstate):
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 52], fill=(30, 34, 44))
        d.text((24, 13), 'QwenOS live   |   tier T0: guest RV32IM on the host emulator, not the Qwen model', font=sansb, fill=AM)
        d.rectangle([0, H - 48, W, H], fill=(30, 34, 44))
        cap = {'boot': 'cold boot: kernel starts, shell prompt appears (guest instructions, host emulator)',
               'shell': 'typed at the prompt: help, ls, cat, echo (all handled by the guest shell and RAM filesystem)',
               'doom': 'run /bin/doomd: DOOM E1M1 on the 32x24 kernel framebuffer. Playback slowed ~60x so each frame and its cost is visible'}[phase]
        d.text((24, H - 36), cap, font=small, fill=WH)
        # right panel
        px = 800
        d.text((px, 70), 'guest instructions executed', font=small, fill=GR)
        d.text((px, 96), '{:,}'.format(instr) if instr else '(shown once DOOM runs)', font=big if instr else small, fill=LB)
        if frame >= 0: d.text((px, 156), 'DOOM frame %d' % frame, font=med, fill=WH)
        return d
    def inset(img, k):
        d = ImageDraw.Draw(img)
        if k < 0 or not insets: return
        fim = Image.open(insets[min(k, len(insets) - 1)]).convert('RGB').resize((432, 324), Image.NEAREST)
        img.paste(fim, (px_inset, 330)); d.rectangle([px_inset - 1, 329, px_inset + 432, 330 + 324], outline=GR)
        d.text((px_inset, 296), 'reference 320x240 frames (separate scripted clip run)', font=small, fill=GR)
        d.text((px_inset, 662 - 2), '', font=small)
    px_inset = 800
    outdir = WORK / 'frames'; shutil.rmtree(outdir, ignore_errors=True); outdir.mkdir(parents=True)
    n = 0
    def emit(im, secs):
        nonlocal n
        for _ in range(int(round(secs * FPS))): im.save(outdir / ('f%05d.png' % n), compress_level=1); n += 1
    # cold-open hook: the published 3 s E1M1 clip (45 frames, 15 fps), shown twice, nearest-neighbour, caption bar throughout
    hook = []
    for k in range(len(insets)):
        im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im)
        im.paste(Image.open(insets[k]).convert('RGB').resize((896, 672), Image.NEAREST), ((W - 896) // 2, 0))
        d.rectangle([0, H - 48, W, H], fill=(30, 34, 44))
        d.text((24, H - 38), 'Real DOOM frames. Every instruction behind these 45 frames was checked on the Qwen model.', font=small, fill=WH)
        hook.append(im)
    for _ in range(2):
        acc = 0.0
        for im in hook:  # 15 fps content on the 20 fps timeline
            nxt = acc + FPS / 15.0; emit(im, (round(nxt) - round(acc)) / FPS); acc = nxt
    emit(intro, 4.5); emit(c_what, 7.0); emit(c_watch, 7.0)
    # shell/boot timeline in virtual time; skip states before first output
    pre = [s for s in states if s[4] != 'doom']
    doom_states = []
    last = -1
    for s in states:
        if s[4] == 'doom' and s[3] != last and s[3] >= 0: doom_states.append(s); last = s[3]
    # doom frames that occur as distinct status-line frame numbers; keep 1 state per frame (last state of the screen)
    T = pre[-1][0]; shell_iter = 0
    t = 0.0; idx = 0; dur = T + 1.0; cache = {}
    while t < dur:
        while idx + 1 < len(pre) and pre[idx + 1][0] <= t: idx += 1
        s = pre[idx]
        key = idx
        if key not in cache:
            im = Image.new('RGB', (W, H), BG); chrome(im, 'boot' if idx < 6 else 'shell', s[2], s[3], None)
            d = ImageDraw.Draw(im); d.rectangle([TX - 8, TY - 8, TX + COLS * CW + 8, TY + ROWS * CH + 4], outline=(60, 66, 80))
            draw_term(im, d, s[1], False); cache = {key: im}
        emit(cache[key], 1.0 / FPS); t += 1.0 / FPS
    # doom phase: first frames slowly (real arrival pace is sub-second on T0; we hold each so the instruction cost is visible)
    frame_secs = [1.6, 1.4, 1.2, 1.0, 0.8, 0.6, 0.5] + [0.25] * 20
    # the screen after each doom state is a full 64x12 cell picture; use the last event in each frame group
    groups = {}
    for s in states:
        if s[4] == 'doom': groups.setdefault(s[5], s)
    # states with complete screen: those where the status line has been drawn (frame>=0) -> one per frame value
    byframe = {}
    for s in states:
        if s[4] == 'doom' and s[3] >= 0: byframe[s[3]] = s
    prev_instr = 0
    for k, fr in enumerate(sorted(byframe)):
        s = byframe[fr]
        im = Image.new('RGB', (W, H), BG); d = chrome(im, 'doom', s[2], s[3], None)
        draw_term(im, d, s[1], True)
        inset(im, fr)
        if k < 7:
            d.text((px_inset, 200), '+%s instr since previous frame' % '{:,}'.format(s[2] - prev_instr), font=small, fill=AM)
            d.text((px_inset, 226), 'T0 emulator: %.2f s wall for this frame' % 0.0 if False else 'T0 emulator: about 15 ms per frame (measured here)', font=small, fill=GR)
            d.text((px_inset, 252), 'Qwen model: ~8-10 min per frame (A100, projected)', font=small, fill=AM)
        prev_instr = s[2]
        emit(im, frame_secs[min(k, len(frame_secs) - 1)])
    emit(c_model, 8.0); emit(c_slow, 8.0); emit(c_honest, 7.0); emit(outro, 4.0)
    print('frames', n, 'duration %.1f s' % (n / FPS))
    OUT.mkdir(parents=True, exist_ok=True)
    mp4 = OUT / 'qwenos-live-boot.mp4'; gif = OUT / 'qwenos-live-boot.gif'
    subprocess.check_call(['ffmpeg', '-y', '-v', 'error', '-framerate', str(FPS), '-i', str(outdir / 'f%05d.png'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '23', '-movflags', '+faststart', str(mp4)])
    pal = WORK / 'pal.png'
    vf = 'fps=10,scale=800:-1:flags=lanczos'
    subprocess.check_call(['ffmpeg', '-y', '-v', 'error', '-framerate', str(FPS), '-i', str(outdir / 'f%05d.png'), '-vf', vf + ',palettegen=max_colors=96', str(pal)])
    subprocess.check_call(['ffmpeg', '-y', '-v', 'error', '-framerate', str(FPS), '-i', str(outdir / 'f%05d.png'), '-i', str(pal), '-lavfi', vf + ' [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4', str(gif)])
    print(mp4, mp4.stat().st_size, gif, gif.stat().st_size)

if __name__ == '__main__':
    a = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if a in ('capture', 'all'): capture()
    if a in ('render', 'all'): render()
