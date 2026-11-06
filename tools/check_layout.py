import sys,struct,subprocess
from pathlib import Path
b=open(sys.argv[1],'rb').read()
assert b[:6]==b'\x7fELF\x01\x01'
entry=struct.unpack_from('<I',b,24)[0]
assert 0x40000<=entry<0x41000,hex(entry)   # kernel owns only the first 4 KiB of ROM
phoff=struct.unpack_from('<I',b,28)[0]
entsize,count=struct.unpack_from('<HH',b,42)
# Exec ROM map: kernel 0x40000, doomd 0x41000-0x77fff, apps 0x78000-0x7ffff.
REGIONS={'kernel':(0x40000,0x41000),'doomd':(0x41000,0x78000),'apps':(0x78000,0x80000)}
code=[]
for i in range(count):
 typ,off,va,pa,fs,ms,flags,align=struct.unpack_from('<IIIIIIII',b,phoff+i*entsize)
 if typ!=1:continue
 assert off+fs<=len(b)
 assert fs<=ms
 assert any(start<=va and va+ms<=end for start,end in [(0x0,0x8000),(0x20000,0x40000),(0x40000,0x80000)]),(hex(va),hex(ms))
 if flags&1:code.append((va,va+ms))
 print('LOAD',hex(va),hex(ms),'flags',flags)
# Core/app RAM contract (RAM_BUDGET.txt): kernel core below doomd RAM base.
def syms(p):
 out=subprocess.check_output(['readelf','-sW',str(p)],text=True)
 return {l.split()[-1]:int(l.split()[1],16) for l in out.splitlines() if len(l.split())>=8 and l.split()[0].rstrip(':').isdigit()}
root=Path(sys.argv[1]).parent
k=syms(root/'kernel.elf')
assert k['__core_end']<=0x98,hex(k['__core_end'])
assert k['__bss_end']<=0x1800,hex(k['__bss_end'])
d=syms(root/'doomd.elf')
assert d['__app_ram_start']==k['__core_end']==0x98 and d['__stack_top']==0x8000
assert d['__bss_end']<=d['__stack_limit'],'doomd data+bss overlaps stack reserve'
k_hi=max(e for s,e in code if s<0x41000); assert k_hi<=0x41000,hex(k_hi)
print('core end',hex(k['__core_end']),'doomd app RAM',hex(d['__app_ram_start']),'..0x8000, data+bss end',hex(d['__bss_end']))
print('PASS: Qwenputer P2/P3 memory layout and entry point',hex(entry))
