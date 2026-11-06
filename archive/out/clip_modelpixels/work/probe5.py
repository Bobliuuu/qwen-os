import pickle,struct
from model_doom_qwen import clone
from upstream_ref import symbols
sy=symbols('/private/tmp/mp/bundle/build/doomd-sym.elf')
sg=pickle.loads(open('orig/seg3.pkl','rb').read())
m=clone(sg['start'])
while m.steps<810705-3000: m.record()
m.ram[sy['q_dump_req']//4]=1
o0=len(m.out); last=m.steps; ln=o0
while m.steps<810705+600000:
    m.record()
    if len(m.out)!=ln: ln=len(m.out); last=m.steps
print('last growth step',last,'bytes',ln-o0)
b=bytes(m.out[o0:ln]); i=0
while i<len(b):
    if b[i]!=1: print('raw',i,b[i]); i+=1; continue
    t=chr(b[i+1]); i+=2
    if t=='P': print('P',b[i]); i+=1
    elif t=='W': print('W',struct.unpack_from('<5H',b,i)); i+=10
    elif t=='D':
        n,=struct.unpack_from('<H',b,i); print('D',n); i+=2+n
    elif t=='E': print('E'); i+=2
    else: print('?',t); break
