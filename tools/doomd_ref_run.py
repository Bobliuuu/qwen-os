#!/usr/bin/env python3
"""Run the merged doomd image on the Python reference CPU + block device until N frame
markers (console byte 0x02) have been seen; prints instruction count at each marker."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from pathlib import Path
from rv32_qwenputer import CPU
from wad_device import WadDevice
elf, disk, nframes = sys.argv[1], sys.argv[2], int(sys.argv[3])
cpu = CPU(elf); dev = WadDevice(cpu, Path(disk).read_bytes())
seen = 0; marks = []; n = 0
while not cpu.halted and len(marks) < nframes:
    cpu.step(); dev.tick()
    if len(cpu.byte_events) != n:
        n = len(cpu.byte_events)
        if cpu.byte_events[-1] == 2: marks.append(cpu.steps)
print('exit', cpu.exitcode, 'steps', cpu.steps)
print('marker steps', marks)
