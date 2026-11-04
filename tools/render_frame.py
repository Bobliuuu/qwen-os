#!/usr/bin/env python3
"""Execute QwenOS in the reference CPU and export the final in-guest framebuffer.
This is guest-memory inspection, not external graphics execution.
Output PGM is readable by ImageMagick, GIMP, PIL, and most image viewers.
"""
import argparse
import re
import subprocess
from pathlib import Path
from rv32_qwenputer import CPU


def main():
    p=argparse.ArgumentParser()
    p.add_argument('elf',nargs='?',default='build/qwenos.elf')
    p.add_argument('--out',default='build/qwenos-frame.pgm')
    a=p.parse_args()
    cpu=CPU(a.elf)
    for _ in range(150_000):
        if cpu.halted:break
        cpu.step()
    if cpu.exitcode!=0:raise SystemExit(f'QwenOS failed (exit={cpu.exitcode})')
    kernel=Path(a.elf).with_name('kernel.elf')
    syms=subprocess.check_output(['readelf','-sW',str(kernel)],text=True)
    match=re.search(r'\b([0-9a-f]{8})\s+768\s+OBJECT\s+(?:LOCAL|GLOBAL)\s+DEFAULT\s+\d+\s+qos_framebuffer\b',syms)
    if not match:raise SystemExit('framebuffer symbol missing')
    addr=int(match.group(1),16)
    frame=cpu.mem[addr:addr+768]
    out=Path(a.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(b'P5\n32 24\n255\n'+frame)
    print(f'Wrote {out} with {len(set(frame))} colors after {cpu.steps} guest instructions')

if __name__=='__main__': main()
