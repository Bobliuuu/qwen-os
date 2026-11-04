#!/usr/bin/env python3
"""Headless interaction with the actual RV32 QwenOS guest on the reference CPU.

The host supplies keyboard events and storage pages, never renders the game.
Sample frames are copies of the guest kernel's own framebuffer RAM.
This is not the Qwen transformer checkpoint.
"""
import argparse
import subprocess
from pathlib import Path
from rv32_qwenputer import CPU
from wad_device import WadDevice, doom_fixture


def symbol(name, elf='build/kernel.elf'):
    out = subprocess.check_output(['readelf', '-sW', elf], text=True)
    matches = [int(s[1], 16) for line in out.splitlines() if (s := line.split())
               and len(s) >= 8 and s[0].rstrip(':').isdigit() and s[-1] == name]
    if len(matches) != 1:
        raise RuntimeError(f'symbol {name}: expected one result, got {len(matches)}')
    return matches[0]


def play(elf, keys='wd', wad=None, limit=1_000_000):
    cpu = CPU(elf)
    dev = WadDevice(cpu, Path(wad).read_bytes() if wad else doom_fixture())
    fb = symbol('qos_framebuffer', str(Path(elf).with_name('kernel.elf')))
    keyboard = symbol('qos_input_mailbox', str(Path(elf).with_name('kernel.elf')))
    frames = []
    cpu.frame_steps = []
    emitted = 0
    num_events = 0
    for _ in range(limit):
        if cpu.halted:
            break
        cpu.step()
        dev.tick()
        # Check only newly output characters to avoid repeatedly decoding history.
        if len(cpu.output) != emitted:
            emitted = len(cpu.output)
            log = ''.join(cpu.output)
            if log.endswith('doom: frame ready\n'):
                frames.append(bytes(cpu.mem[fb:fb + 32 * 24]))
                cpu.frame_steps.append(cpu.steps)
                if num_events < len(keys):
                    cpu.store(keyboard + 4 + (num_events & 3), 1, ord(keys[num_events]))
                    cpu.store(keyboard, 4, num_events + 1)
                    num_events += 1
    log = ''.join(cpu.output)
    if not cpu.halted or cpu.exitcode != 0 or 'QWENOS_BOOT_OK' not in log:
        raise RuntimeError(f'incomplete guest run: {cpu.steps} steps, exit={cpu.exitcode}')
    if len(frames) != min(5, len(keys)+1):
        raise RuntimeError(f'expected {min(5,len(keys)+1)} frames, found {len(frames)}')
    return cpu, dev, frames


def to_rgb(frame):
    """Decode the doom app pixel format: bits7-6 class, bits5-0 brightness."""
    tint = [(1.0, 0.9, 0.75), (0.55, 0.6, 0.45), (0.5, 0.55, 0.75), (0.35, 0.5, 1.0)]
    out = bytearray()
    for v in frame:
        cls, b = v >> 6, v & 63
        if cls == 3:
            r, g, bl = 90, 130, 230
        else:
            k = min(255, b * 4)
            r, g, bl = (int(k * t) for t in tint[cls])
        out += bytes((r, g, bl))
    return bytes(out)


def write_png(path, frame, scale=16):
    import struct, zlib
    w, h = 32, 24
    rgb = to_rgb(frame)
    rows = bytearray()
    for y in range(h):
        row = b''.join(rgb[(y * w + x) * 3:(y * w + x) * 3 + 3] * scale for x in range(w))
        rows += (b'\0' + row) * scale
    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d))
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w * scale, h * scale, 8, 2, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(bytes(rows))) + chunk(b'IEND', b''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--elf', default='build/qwenos.elf')
    ap.add_argument('--keys', default='wd', help='at most four WASD key events')
    ap.add_argument('--wad', help='optional local IWAD/PWAD file')
    ap.add_argument('--output', default='build/interactive')
    ap.add_argument('--png', action='store_true', help='also write coloured PNGs')
    ap.add_argument('--limit', type=int, default=1_000_000)
    args = ap.parse_args()
    if len(args.keys) > 4 or any(k not in 'wasd' for k in args.keys):
        ap.error('keys must be 0-4 characters from wasd')
    cpu, dev, frames = play(args.elf, args.keys, args.wad, args.limit)
    prefix = Path(args.output)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for idx, frame in enumerate(frames):
        prefix.with_name(f'{prefix.name}-{idx:02}.pgm').write_bytes(b'P5\n32 24\n255\n' + frame)
        if args.png:
            write_png(prefix.with_name(f'{prefix.name}-{idx:02}.png'), frame)
    print(f'{len(frames)} guest frames, {cpu.steps} guest instructions, '
          f'{len(dev.reads)} asset reads, exit={cpu.exitcode}')
    fs = cpu.frame_steps
    print('instructions at each frame:', fs, 'per-frame deltas:', [fs[0]] + [fs[i] - fs[i-1] for i in range(1, len(fs))])
    print('frame differences:', [sum(a != b for a, b in zip(frames[i], frames[i+1]))
                                 for i in range(len(frames)-1)])


if __name__ == '__main__':
    main()

