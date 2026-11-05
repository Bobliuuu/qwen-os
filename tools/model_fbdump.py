#!/usr/bin/env python3
"""Model-decoded DOOM pixels: split one frame's serial LCD dump into model sub-segments, then decode the model's bytes.

  split:  tools/model_fbdump.py split --elf E --sym-elf doomd-sym.elf --snaps DIR --seg N --parts P --out OUTDIR --first-index I
          Loads the verified host start state of the frame (seg<N>.pkl, the state right before the frame), sets the guest
          variable q_dump_req=1 in RAM (the guest then arms its own serial LCD dump for that frame: it streams every pump
          window over the console, ~32k bytes; typing the 'p' key panics in this build), runs the host reference once and
          cuts the run into P sub-segments at pcs not yet executed in the sub-segment (ROM ebreak breakpoints, exactly like
          the stop hook), writing OUTDIR/seg<I..I+P-1>.pkl for tools/model_doom_qwen.py --load-starts. Every sub-segment is
          then run on the real model with the lockstep oracle; the console bytes are the model's own BYTE tokens (<out>.model).
  decode: tools/model_fbdump.py decode --model-bytes F.. --frames 14,13 --frame-lengths 32100,.. --wad freedoom1.wad
          --emu-frames out/clip/frames --out DIR
          Cuts the model's byte stream per frame, decodes with tools/lowres_frames.py (palette index -> RGB through the
          IWAD PLAYPAL on the host: the only host-side conversion) and compares with the emulator frame PNGs.
"""
import argparse, pickle, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))


def split(a):
    from model_doom_qwen import clone, breakpoint_at, oracle_run
    from upstream_ref import symbols
    sg = pickle.loads((Path(a.snaps) / f'seg{a.seg}.pkl').read_bytes())
    m = clone(sg['start'])   # carries an ebreak on the segment's own stop pc (ends the last sub-segment)
    m.ram[symbols(a.sym_elf)['q_dump_req'] // 4] = 1   # host arms the guest's own serial dump for this frame
    tot, _, _ = oracle_run(clone(m))
    total = tot - 1
    print(f'frame seg {a.seg}: {total} instr with dump armed', flush=True)
    outd = Path(a.out); outd.mkdir(parents=True, exist_ok=True)
    done, base = 0, m.steps
    for k in range(a.parts):
        start = clone(m); s0 = m.steps
        if k == a.parts - 1:
            stop_pc = None
        else:
            target = base + (k + 1) * total // a.parts
            visited = set()
            while m.steps < target or m.pc in visited:
                visited.add(m.pc); m.record()
                if m.halted: raise RuntimeError('halted before split')
            stop_pc = m.pc
            breakpoint_at(start, stop_pc)
        i, t, out = oracle_run(clone(start))
        instr = i - 1
        if stop_pc is not None:
            assert m.steps - s0 == instr, (m.steps - s0, instr)
        else:
            while not m.halted and m.steps - s0 < instr: m.record()
        d = dict(index=a.first_index + k, start=start, start_steps=s0, stop_pc=stop_pc, instr=instr, tokens=t, out=out,
                 reason='split', rom_chunk=None, markers=0)
        (outd / f'seg{a.first_index + k}.pkl').write_bytes(pickle.dumps(d, protocol=5))
        done += instr
        print(f'  part {k}: {instr} instr, {t} tokens, {len(out)} console bytes', flush=True)
    assert done == total, (done, total)


def png_rows(path):
    import zlib, struct
    d = Path(path).read_bytes(); i, idat = 8, b''
    while i < len(d):
        n = struct.unpack('>I', d[i:i + 4])[0]
        if d[i + 4:i + 8] == b'IDAT': idat += d[i + 8:i + 8 + n]
        i += 12 + n
    r = zlib.decompress(idat); w = 320 * 3 + 1
    return [r[y * w + 1:(y + 1) * w] for y in range(240)]


def painted_rows(buf):
    """Rows covered by the window records of one dump stream (a frame's dump only holds the windows the engine redrew)."""
    import struct
    rows, i = set(), 0
    while i < len(buf):
        if buf[i] != 1: i += 1; continue
        t = chr(buf[i + 1]); i += 2
        if t == 'P': i += 1
        elif t == 'W':
            x0, x1, y0, y1, fl = struct.unpack_from('<5H', buf, i); i += 10; rows.update(range(y0, y1 + 1))
        elif t == 'D':
            n, = struct.unpack_from('<H', buf, i); i += 2 + n
        elif t == 'E': i += 2
    return rows


def decode(a):
    import subprocess, hashlib
    buf = b''.join(Path(f).read_bytes() for f in a.model_bytes)
    lens = [int(x) for x in a.frame_lengths.split(',')]
    assert sum(lens) == len(buf), (sum(lens), len(buf))
    outd = Path(a.out); outd.mkdir(parents=True, exist_ok=True)
    table, pos = [], 0
    for fr, n in zip([int(x) for x in a.frames.split(',')], lens):
        chunk = buf[pos:pos + n]; pos += n
        sp = outd / f'model_stream_{fr:02d}.bin'; sp.write_bytes(chunk)
        subprocess.check_call([sys.executable, str(Path(__file__).parent / 'lowres_frames.py'), str(sp), a.wad,
                               str(outd / f'_f{fr:02d}'), '1', 'all'], stdout=subprocess.DEVNULL)
        png = outd / f'frame_{fr:02d}_model.png'
        (outd / f'_f{fr:02d}-000.png').replace(png)
        pr, rr = png_rows(png), png_rows(Path(a.emu_frames) / f'frame_{fr:02d}.png')
        cov = sorted(painted_rows(chunk))
        bad = [y for y in cov if pr[y] != rr[y]]
        full = sum(1 for y in range(240) if pr[y] != rr[y])
        table.append((fr, n, len(cov), len(bad), 240 - len(cov), full, hashlib.md5(chunk).hexdigest()))
        print(f'frame {fr:02d}: model bytes {n}, rows painted by the dump {len(cov)}/240, mismatching painted rows {len(bad)}, '
              f'unpainted rows (status bar not redrawn this frame) {240 - len(cov)}, full-frame mismatching rows {full}', flush=True)
    return table


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('split')
    for n in ('elf', 'sym_elf', 'snaps', 'out'): s.add_argument('--' + n.replace('_', '-'), required=True)
    s.add_argument('--seg', type=int, required=True); s.add_argument('--parts', type=int, default=6); s.add_argument('--first-index', type=int, required=True)
    d = sub.add_parser('decode'); d.add_argument('--model-bytes', nargs='+', required=True); d.add_argument('--out', required=True)
    for n in ('frames', 'frame-lengths', 'wad', 'emu-frames'): d.add_argument('--' + n, required=True)
    a = ap.parse_args()
    split(a) if a.cmd == 'split' else decode(a)
