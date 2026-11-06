#!/usr/bin/env python3
"""Export the guest framebuffer from a real RV32 run using synthetic DOOM WAD geometry."""
import argparse
import subprocess
import sys
from pathlib import Path
from wad_device import run,doom_fixture

def kernel_symbol(path,name):
    output=subprocess.check_output(['readelf','-sW',path],text=True)
    found=[int(line.split()[1],16) for line in output.splitlines()
           if len(line.split())>=8 and line.split()[-1]==name]
    if len(found)!=1:raise ValueError(f'could not uniquely resolve {name}')
    return found[0]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--elf',default='build/qwenos.elf')
    p.add_argument('--wad',help='Optional externally supplied WAD')
    p.add_argument('--out',default='build/doom-frame.pgm')
    a=p.parse_args()
    cpu,dev,log=run(a.elf,a.wad)
    if cpu.exitcode!=0 or 'doom: WAD map geometry rendered' not in log:
        raise RuntimeError('guest did not render a WAD map')
    elf=Path(a.elf)
    framebuffer=kernel_symbol(elf.with_name('kernel.elf'),'framebuffer')
    pixels=bytes(cpu.mem[framebuffer:framebuffer+32*24])
    Path(a.out).write_bytes(b'P5\n32 24\n255\n'+pixels)
    print(f'{a.out}: 32x24 guest framebuffer, {cpu.steps} RISC-V instructions, {len(dev.reads)} disk requests, {len(set(pixels))} shades')

if __name__=='__main__': main()
