"""External read-only virtual disk for QwenOS's guest RAM mailbox.

The host ONLY copies requested data bytes into guest memory: all WAD parsing,
validation and application control flow occur as guest RV32 instructions.
To run with an arbitrary WAD:
  python3 tools/wad_device.py build/qwenos.elf --wad /path/to/DOOM1.WAD
The included synthetic fixture is a tiny *valid WAD directory/header layout*
placed inside a 4MiB virtual disk; it is not DOOM game content.
"""
import argparse
import struct
import subprocess
from pathlib import Path
from rv32_qwenputer import CPU

DEMO_NAME=b'QOSDEMO\0'
DEMO_DATA=b'QwenOS paged WAD data test pass!'
DEMO_LUMP_OFFSET=0x210000
DEMO_DIRECTORY_OFFSET=0x300000
DEMO_DISK_SIZE=0x400000

def fixture() -> bytes:
    disk=bytearray(DEMO_DISK_SIZE)
    disk[:12]=struct.pack('<4sII',b'IWAD',1,DEMO_DIRECTORY_OFFSET)
    disk[DEMO_LUMP_OFFSET:DEMO_LUMP_OFFSET+len(DEMO_DATA)]=DEMO_DATA
    disk[DEMO_DIRECTORY_OFFSET:DEMO_DIRECTORY_OFFSET+16]=struct.pack('<II8s',DEMO_LUMP_OFFSET,len(DEMO_DATA),DEMO_NAME)
    return bytes(disk)

def doom_fixture() -> bytes:
    """A genuine-format E1M1 lump layout (tiny synthetic square room).

    This is deliberately NOT a stock DOOM asset and doesn't contain id Software
    textures or game logic. It exercises standard THINGS/LINEDEFS/VERTEXES.
    """
    disk=bytearray(fixture())
    things=struct.pack('<hhhhh',0,0,0,1,7)  # player 1 in center
    vertices=b''.join(struct.pack('<hh',x,y) for x,y in
                      [(-64,-64),(128,-64),(128,64),(-64,64)])
    linedefs=b''.join(struct.pack('<7H',a,b,1,0,0,0,0xffff)
                       for a,b in [(0,1),(1,2),(2,3),(3,0)])
    lumps=[(b'QOSDEMO\0',DEMO_LUMP_OFFSET,DEMO_DATA),
           (b'E1M1\0\0\0\0',0,b''),
           (b'THINGS\0\0',0x210100,things),
           (b'LINEDEFS',0x210200,linedefs),
           (b'SIDEDEFS',0,b''),
           (b'VERTEXES',0x210300,vertices),
           (b'SEGS\0\0\0\0',0,b''),
           (b'SSECTORS',0,b''),
           (b'NODES\0\0\0',0,b''),
           (b'SECTORS\0',0,b''),
           (b'REJECT\0\0',0,b''),
           (b'BLOCKMAP',0,b'')]
    disk[:12]=struct.pack('<4sII',b'IWAD',len(lumps),DEMO_DIRECTORY_OFFSET)
    for i,(name,off,body) in enumerate(lumps):
        if body:disk[off:off+len(body)]=body
        disk[DEMO_DIRECTORY_OFFSET+i*16:DEMO_DIRECTORY_OFFSET+(i+1)*16]=struct.pack('<II8s',off,len(body),name)
    return bytes(disk)

class WadDevice:
    def __init__(self,cpu:CPU,data:bytes):
        self.cpu=cpu
        self.data=data
        if 'qos_disk_mailbox' in cpu.sym:
            self.base=cpu.sym['qos_disk_mailbox']
        else:
            kernel_elf=Path(cpu.elf_path).with_name('kernel.elf')
            sym=subprocess.check_output(['readelf','-sW',str(kernel_elf)],text=True)
            matches=[int(line.split()[1],16) for line in sym.splitlines()
                     if len(line.split())>=8 and line.split()[-1]=='qos_disk_mailbox']
            if len(matches)!=1: raise RuntimeError('mailbox symbol not found in kernel ELF')
            self.base=matches[0]
        self.last_request=0
        self.reads=[]

    def word(self,off):
        return int.from_bytes(self.cpu.mem[self.base+off:self.base+off+4],'little')

    def tick(self):
        seq=self.word(0)
        if seq==0 or seq==self.last_request:
            return
        offset=self.word(4)
        length=self.word(8)
        if not (0 < length <= 256):
            raise ValueError('corrupt guest block request')
        self.last_request=seq
        good=offset<=len(self.data) and length<=len(self.data)-offset
        if good:
            for i,byte in enumerate(self.data[offset:offset+length]):
                self.cpu.store(self.base+20+i,1,byte)
        self.cpu.store(self.base+16,4,1 if good else 2)  # status
        self.cpu.store(self.base+12,4,seq)  # release response LAST
        self.reads.append((offset,length,good))


def run(elf,wad=None,max_steps=1500000):
    cpu=CPU(elf)
    device=WadDevice(cpu,Path(wad).read_bytes() if wad else doom_fixture())
    for _ in range(max_steps):
        if cpu.halted:
            break
        cpu.step()
        device.tick()
    output=''.join(cpu.output)
    return cpu,device,output

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('elf',nargs='?',default='build/qwenos.elf')
    ap.add_argument('--wad')
    ap.add_argument('--max-steps',type=int,default=1500000)
    args=ap.parse_args()
    cpu,dev,out=run(args.elf,args.wad,args.max_steps)
    print(out,end='')
    print(f'[rv32 instructions={cpu.steps} exit={cpu.exitcode} disk reads={dev.reads}]')
    if cpu.exitcode!=0 or not cpu.halted:
        raise SystemExit(1)
    if not args.wad and ('asset: WAD read and verified' not in out or 'doom: WAD map geometry rendered' not in out):
        raise SystemExit(2)
if __name__=='__main__':main()
