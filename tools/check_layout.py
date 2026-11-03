import sys,struct
b=open(sys.argv[1],'rb').read()
assert b[:6]==b'\x7fELF\x01\x01'
entry=struct.unpack_from('<I',b,24)[0]
assert 0x40000<=entry<0x80000,hex(entry)
phoff=struct.unpack_from('<I',b,28)[0]
entsize,count=struct.unpack_from('<HH',b,42)
for i in range(count):
 typ,off,va,pa,fs,ms,flags,align=struct.unpack_from('<IIIIIIII',b,phoff+i*entsize)
 if typ!=1:continue
 assert off+fs<=len(b)
 assert fs<=ms
 assert any(start<=va and va+ms<=end for start,end in [(0x100,0x8000),(0x20000,0x40000),(0x40000,0x80000)]),(hex(va),hex(ms))
 print('LOAD',hex(va),hex(ms),'flags',flags)
print('PASS: Qwenputer P2/P3 memory layout and entry point',hex(entry))
