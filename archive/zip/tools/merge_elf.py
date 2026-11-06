#!/usr/bin/env python3
"""Merge separately linked fixed-ROM ELF32 apps into one Qwenputer snapshot ELF.
No host-side execution of guest code, no ELF loader inside guest; independent
modules are preloaded at known addresses to satisfy immutable executable ROM.
"""
import struct
import sys
from pathlib import Path


def parse(data):
    if data[:6] != b'\x7fELF\x01\x01':
        raise ValueError('expected little-endian ELF32')
    if struct.unpack_from('<H', data, 18)[0] != 243:
        raise ValueError('expected RISC-V ELF')
    entry, phoff = struct.unpack_from('<II', data, 24)
    entsize, count = struct.unpack_from('<HH', data, 42)
    if entsize != 32 or phoff + count * entsize > len(data):
        raise ValueError('bad ELF program headers')
    segments=[]
    for i in range(count):
        typ, off, va, pa, fs, ms, flags, align=struct.unpack_from('<8I',data,phoff+i*entsize)
        if typ!=1 or not ms: continue
        if fs>ms or off+fs>len(data):raise ValueError('malformed load segment')
        segments.append((va, bytes(data[off:off+fs])+bytes(ms-fs), flags))
    return entry,segments


def merge(output, inputs):
    entries=[]
    for f in inputs:
        ent,segs=parse(Path(f).read_bytes()); entries.append((ent,segs))
    entry=entries[0][0]
    assert entry>=0x40000 and entry<0x60000,hex(entry)
    collected=[]
    for ent,segs in entries:
        for va,data,flags in segs:
            if not any(lo<=va and va+len(data)<=hi for lo,hi in ((0x100,0x8000),(0x20000,0x40000),(0x40000,0x80000))):
                raise ValueError(f'bad segment {va:#x}+{len(data)}')
            for prev,blob,_ in collected:
                if va<prev+len(blob) and prev<va+len(data):
                    raise ValueError(f'overlapping segments {va:#x} and {prev:#x}')
            collected.append((va,data,flags))
    # Independently linked applications must have executable code at their ABI addresses.
    for expected in (0x60000,0x68000,0x70000,0x78000,0x7c000):
        if not any(va<=expected<va+len(data) and flags&1 for va,data,flags in collected):
            raise ValueError(f'missing app ROM at {expected:#x}')
    collected.sort()
    out=bytearray(52+32*len(collected));out[:52]=Path(inputs[0]).read_bytes()[:52]
    struct.pack_into('<I',out,24,entry);struct.pack_into('<I',out,28,52)
    struct.pack_into('<I',out,32,0);struct.pack_into('<H',out,42,32);struct.pack_into('<H',out,44,len(collected))
    for i,(va,data,flags) in enumerate(collected):
        off=(len(out)+15)&~15
        out.extend(bytes(off-len(out)))
        out.extend(data)
        struct.pack_into('<8I',out,52+i*32,1,off,va,va,len(data),len(data),flags,4)
    Path(output).write_bytes(out)
    return entry, collected

if __name__=='__main__':
    e,segs=merge(sys.argv[1],sys.argv[2:])
    print(f'Merged {len(segs)} load regions, entry {e:#x}, size {Path(sys.argv[1]).stat().st_size} bytes')
