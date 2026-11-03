#!/usr/bin/env python3
"""Execute the actual Qwenputer reference CPU against the merged QwenOS ELF.

Run with the cloned upstream repository available on PYTHONPATH:
 PYTHONPATH=/path/to/qwenputer/experimental/riscv \
   python tools/upstream_ref.py build/qwenos.elf --wad-device

--wad-device supplies data through an external virtual block-device mailbox;
it does not execute application code. For a real WAD, pass --wad /path/to/DOOM1.WAD.
The reference machine is not the compiled Qwen transformer checkpoint.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from wad_device import fixture


def symbols(kernel_elf):
    output=subprocess.check_output(['readelf','-sW',str(kernel_elf)],text=True)
    return {line.split()[-1]:int(line.split()[1],16) for line in output.splitlines()
            if len(line.split())>=8 and line.split()[0].rstrip(':').isdigit()}

class ReferenceDiskDevice:
    """Read/write a mailbox in Qwenputer's *actual* word-array RAM representation."""
    def __init__(self,machine,mailbox_address,data):
        self.m=machine
        self.base=mailbox_address
        self.data=data
        self.last_request=0
        self.reads=[]

    def get_u32(self,address):
        assert 0<=address<=0x7ffc and address%4==0
        return self.m.ram[address//4]

    def put_u32(self,address,value):
        assert 0<=address<=0x7ffc and address%4==0
        self.m.ram[address//4]=value&0xffffffff

    def put_byte(self,address,value):
        assert 0<=address<0x8000
        idx=address//4
        shift=8*(address%4)
        self.m.ram[idx]=(self.m.ram[idx]&~(0xff<<shift))|((value&255)<<shift)

    def tick(self):
        seq=self.get_u32(self.base)
        if not seq or seq==self.last_request:return
        self.last_request=seq
        offset=self.get_u32(self.base+4)
        n=self.get_u32(self.base+8)
        if not 0<n<=256:
            raise ValueError('invalid requested sector length')
        valid=offset<=len(self.data) and n<=len(self.data)-offset
        if valid:
            for i,b in enumerate(self.data[offset:offset+n]):
                self.put_byte(self.base+20+i,b)
        self.put_u32(self.base+16,1 if valid else 2)
        self.put_u32(self.base+12,seq)  # release flag, written last
        self.reads.append((offset,n,valid))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('elf',nargs='?',default='build/qwenos.elf')
    p.add_argument('--kernel-elf',default=None)
    p.add_argument('--max-instructions',type=int,default=250000)
    p.add_argument('--json',action='store_true')
    p.add_argument('--wad-device',action='store_true')
    p.add_argument('--wad',default=None)
    a=p.parse_args()
    try:
        from chipformer.rv import elf,ref
    except ImportError as exc:
        sys.exit('Missing upstream Qwenputer. Set PYTHONPATH to qwenputer/experimental/riscv: '+str(exc))
    m=ref.Machine.from_program(elf.program(a.elf))
    dev=None
    if a.wad_device or a.wad:
        kelf=a.kernel_elf or str(Path(a.elf).with_name('kernel.elf'))
        dev=ReferenceDiskDevice(m,symbols(kelf)['qos_disk_mailbox'],Path(a.wad).read_bytes() if a.wad else fixture())
    records=0
    toks=1
    while not m.halted and m.steps<a.max_instructions:
        t=m.record()
        records+=1
        toks+=len(t)
        if m.fault:break
        if dev:dev.tick()
    msg=m.out.decode('latin1')
    report=dict(halted=m.halted,exit_code=m.exit_code,fault=m.fault,instructions=m.steps,
                records=records,tokens=toks,disk_reads=dev.reads if dev else [],output=msg)
    if a.json:print(json.dumps(report,indent=2))
    else:
        print(msg,end='')
        print(f'\n[upstream Qwenputer reference: {m.steps} instructions, {toks} tokens, exit={m.exit_code}, fault={m.fault}]')
        if dev:print('Disk reads:',dev.reads)
    if not m.halted or m.exit_code!=0 or m.fault is not None or 'QWENOS_BOOT_OK' not in msg or 'raycast: frame rendered' not in msg:
        sys.exit(1)
    if dev and not a.wad and 'asset: WAD read and verified' not in msg:
        sys.exit(2)

if __name__=='__main__':main()
