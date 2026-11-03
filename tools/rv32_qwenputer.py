#!/usr/bin/env python3
"""Minimal independent RV32IM reference executor for QwenOS, not Qwenputer."""
import argparse, struct, subprocess
MASK=0xffffffff

def signed(v):
 v &= MASK
 return v-(1<<32) if v&0x80000000 else v

def sext(v,b):
 return v-(1<<b) if v&(1<<(b-1)) else v

class CPU:
 def __init__(self, elf):
  self.elf_path=str(elf)
  self.mem=bytearray(0x80000);self.reg=[0]*32;self.pc=0;self.steps=0
  from pathlib import Path
  data=Path(elf).read_bytes()
  assert data[:4]==b'\x7fELF' and data[4]==1 and data[5]==1
  self.output=[];self.exitcode=None;self.halted=False
  self.pc=struct.unpack_from('<I',data,24)[0]
  phoff=struct.unpack_from('<I',data,28)[0]
  entsize,count=struct.unpack_from('<HH',data,42)
  for i in range(count):
   t,off,va,pa,fs,ms,flags,align=struct.unpack_from('<IIIIIIII',data,phoff+i*entsize)
   if t!=1:continue
   assert va+ms<=len(self.mem) and off+fs<=len(data)
   self.mem[va:va+fs]=data[off:off+fs]
  symbols=subprocess.check_output(['readelf','-sW',elf],text=True)
  self.sym={line.split()[-1]:int(line.split()[1],16) for line in symbols.splitlines() if len(line.split())>=8 and line.split()[0].rstrip(':').isdigit()}
 def load(self,a,n):
  if not ((0 <= a and a+n <= 0x8000) or (0x20000<=a and a+n<=0x40000)):raise RuntimeError(f'read outside Qwenputer data memory {a:#x}+{n}')
  return int.from_bytes(self.mem[a:a+n],'little')
 def store(self,a,n,v):
  if a<0 or a+n>0x8000:raise RuntimeError(f'write outside Qwenputer RAM {a:#x}+{n}')
  self.mem[a:a+n]=(v&((1<<(n*8))-1)).to_bytes(n,'little')
 def step(self):
  p=self.pc
  if not 0x40000<=p<=0x7fffc or p%4:raise RuntimeError(f'bad instruction fetch {p:#x}')
  w=int.from_bytes(self.mem[p:p+4],'little')
  if w&3!=3:raise RuntimeError(f'compressed/invalid opcode {p:#x}: {w:#x}')
  op=w&127;rd=(w>>7)&31;f=(w>>12)&7;rs1=(w>>15)&31;rs2=(w>>20)&31;f7=w>>25
  a=self.reg[rs1];b=self.reg[rs2];v=0;nextpc=(p+4)&MASK
  imm_i=sext(w>>20,12);imm_s=sext(((w>>25)<<5)|((w>>7)&31),12)
  if op==0x37:v=w&0xfffff000
  elif op==0x17:v=p+(w&0xfffff000)
  elif op==0x6f:
   imm=sext(((w>>31)<<20)|(((w>>12)&255)<<12)|(((w>>20)&1)<<11)|(((w>>21)&1023)<<1),21)
   v=nextpc;nextpc=(p+imm)&MASK
  elif op==0x67:v=nextpc;nextpc=(a+imm_i)&~1&MASK
  elif op==0x63:
   imm=sext(((w>>31)<<12)|(((w>>7)&1)<<11)|(((w>>25)&63)<<5)|(((w>>8)&15)<<1),13)
   cond={0:a==b,1:a!=b,4:signed(a)<signed(b),5:signed(a)>=signed(b),6:a<b,7:a>=b}.get(f)
   if cond is None:raise RuntimeError('branch funct3')
   if cond:nextpc=(p+imm)&MASK
  elif op==0x03:
   n={0:1,1:2,2:4,4:1,5:2}.get(f)
   if not n:raise RuntimeError('load funct3')
   v=self.load((a+imm_i)&MASK,n)
   if f in (0,1):v=sext(v,n*8)
  elif op==0x23:
   n={0:1,1:2,2:4}.get(f)
   if not n:raise RuntimeError('store funct3')
   self.store((a+imm_s)&MASK,n,b)
  elif op==0x13:
   if f==0:v=a+imm_i
   elif f==2:v=int(signed(a)<imm_i)
   elif f==3:v=int(a<(imm_i&MASK))
   elif f==4:v=a^imm_i
   elif f==6:v=a|imm_i
   elif f==7:v=a&imm_i
   elif f==1:v=a<<(b if False else (w>>20)&31)
   elif f==5:v=(signed(a) if f7==0x20 else a)>>((w>>20)&31)
   else:raise RuntimeError('opimm')
  elif op==0x33:
   sh=b&31
   if f7==1:
    if f==0:v=a*b
    elif f==1:v=(signed(a)*signed(b))>>32
    elif f==2:v=(signed(a)*b)>>32
    elif f==3:v=(a*b)>>32
    elif f==4:v=MASK if b==0 else (0x80000000 if a==0x80000000 and b==MASK else (abs(signed(a))//abs(signed(b)))*(-1 if (signed(a)<0) != (signed(b)<0) else 1))
    elif f==5:v=MASK if b==0 else a//b
    elif f==6:v=a if b==0 else (a if a==0x80000000 and b==MASK else signed(a)-(int((abs(signed(a))//abs(signed(b)))*(-1 if (signed(a)<0)!=(signed(b)<0) else 1))*signed(b)))
    elif f==7:v=a if b==0 else a%b
   elif f7 in (0,0x20):
    if f==0:v=a-b if f7 else a+b
    elif f==1:v=a<<sh
    elif f==2:v=int(signed(a)<signed(b))
    elif f==3:v=int(a<b)
    elif f==4:v=a^b
    elif f==5:v=signed(a)>>sh if f7 else a>>sh
    elif f==6:v=a|b
    elif f==7:v=a&b
    else:raise RuntimeError('alu funct3')
   else:raise RuntimeError(f'alu funct7 {f7}')
  elif op==0x0f:pass
  elif op==0x73:
   if self.reg[17]==1:
    self.output.append(chr(self.reg[10]&255))
   elif self.reg[17]==93:
    self.exitcode=self.reg[10];self.halted=True
   else:raise RuntimeError(f'unsupported ecall {self.reg[17]} at {p:#x}')
  else:raise RuntimeError(f'unsupported opcode {op:#x} at {p:#x}, word {w:#x}')
  if rd and op not in (0x63,0x23,0x0f):self.reg[rd]=v&MASK
  self.pc=nextpc;self.steps+=1
 def run(self,limit):
  for _ in range(limit):
   if self.halted:break
   self.step()
  log=''.join(self.output)
  print('steps:',self.steps,'exit:',self.exitcode,'\n'+log)
  assert self.halted and self.exitcode==0,'guest failed to exit cleanly'
  assert 'QWENOS_BOOT_OK' in log and 'hello from QwenOS' in log and 'paint: framebuffer changed' in log and 'raycast: frame rendered' in log and 'QwenOS /bin/sh: pid 1' in log
  print('PASS: kernel + separately linked shell/paint/raycast on RV32IM reference memory map')
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('elf');ap.add_argument('--limit',type=int,default=500000);args=ap.parse_args();CPU(args.elf).run(args.limit)
