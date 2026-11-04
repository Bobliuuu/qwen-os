#!/usr/bin/env python3
"""fh.py out.bin -> prints md5 per 'E' (canvas+palette); optional prefix saves PNGs of unique frames"""
import sys,hashlib
d=open(sys.argv[1],'rb').read()
i=0;cur=0;win=None;col=0;canvas=bytearray(320*240);n=0;res=[]
L=len(d)
while i<L:
    if d[i]!=1: i+=1; continue
    t=d[i+1]; i+=2
    if t==80: cur=d[i]; i+=1            # P
    elif t==87:                          # W
        win=(d[i]|d[i+1]<<8,d[i+2]|d[i+3]<<8,d[i+4]|d[i+5]<<8,d[i+6]|d[i+7]<<8,d[i+8]|d[i+9]<<8); i+=10; col=win[0]
    elif t==68:                          # D
        nb=d[i]|d[i+1]<<8; i+=2
        if i+nb>L: break
        x0,x1,y0,y1,fl=win;h=y1-y0+1
        for c in range(nb//h):
            canvas[(y0)*320+col:(y1+1)*320+col:320]=d[i+c*h:i+c*h+h]
            col+=1
            if col>x1: col=x0
        i+=nb
    elif t==69:                          # E
        i+=2
        res.append(hashlib.md5(bytes([cur])+bytes(canvas)).hexdigest()[:12])
print(len(res))
# dedupe consecutive
out=[]
for h in res:
    if not out or out[-1]!=h: out.append(h)
open(sys.argv[2],'w').write('\n'.join(out)+'\n')
print(len(out),'unique-consecutive')
