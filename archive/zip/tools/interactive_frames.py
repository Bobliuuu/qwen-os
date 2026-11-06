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
    fb = symbol('framebuffer', str(Path(elf).with_name('kernel.elf')))
    keyboard = symbol('qos_input_mailbox', str(Path(elf).with_name('kernel.elf')))
    frames = []
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
                if num_events < len(keys):
                    cpu.store(keyboard + 4, 4, ord(keys[num_events]))
                    cpu.store(keyboard, 4, 100 + num_events)
                    num_events += 1
    log = ''.join(cpu.output)
    if not cpu.halted or cpu.exitcode != 0 or 'QWENOS_BOOT_OK' not in log:
        raise RuntimeError(f'incomplete guest run: {cpu.steps} steps, exit={cpu.exitcode}')
    if len(frames) != min(5, len(keys)+1):
        raise RuntimeError(f'expected {min(5,len(keys)+1)} frames, found {len(frames)}')
    return cpu, dev, frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--elf', default='build/qwenos.elf')
    ap.add_argument('--keys', default='wd', help='at most four WASD key events')
    ap.add_argument('--wad', help='optional local IWAD/PWAD file')
    ap.add_argument('--output', default='build/interactive')
    args = ap.parse_args()
    if len(args.keys) > 4 or any(k not in 'wasd' for k in args.keys):
        ap.error('keys must be 0-4 characters from wasd')
    cpu, dev, frames = play(args.elf, args.keys, args.wad)
    prefix = Path(args.output)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for idx, frame in enumerate(frames):
        prefix.with_name(f'{prefix.name}-{idx:02}.pgm').write_bytes(b'P5\n32 24\n255\n' + frame)
    print(f'{len(frames)} guest frames, {cpu.steps} guest instructions, '
          f'{len(dev.reads)} asset reads, exit={cpu.exitcode}')
    print('frame differences:', [sum(a != b for a, b in zip(frames[i], frames[i+1]))
                                 for i in range(len(frames)-1)])


if __name__ == '__main__':
    main()
