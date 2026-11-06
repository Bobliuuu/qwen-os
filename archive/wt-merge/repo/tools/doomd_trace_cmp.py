#!/usr/bin/env python3
"""Field-by-field compare of the guest's hashed state of ONE tic with the host oracle's.

  # guest: QTRACE=<tic> prints every hashed value of that tic ("T name idx value") on the console
  DOOMD_MODE=1 QHASH=1 QTRACE=71 EXTRA_CF=-DQ_DUMP_ALL ports/doomdmc/build.sh OUT ; (merge, run rv32_fast)
  # oracle: tools/build_oracle_mac.sh $DMC ; $DMC/build/oracle/dg_oracle -iwad freedoom1.wad -playdemo demo1 \
  #             --tics 80 --hash-dump 71 d71.txt
  doomd_trace_cmp.py guest_out.bin d71.txt

Known benign difference: the guest lists dropped items / puffs in store order, the oracle in spawn order,
so mo.* records appear swapped (same multiset); everything else must be equal.
"""
import sys,re
bin_,orc=sys.argv[1],sys.argv[2]
d=open(bin_,'rb').read().decode('latin1')
g=[]
for m in re.finditer(r'^T (\S+) (\d+) (-?\d+)$',d,re.M):
    v=int(m.group(3)); v=v-(1<<32) if v>=1<<31 else v
    g.append((m.group(1),int(m.group(2)),v))
o=[]
for l in open(orc):
    l=l.strip()
    if l.startswith('hash'):continue
    m=re.match(r'([\w.]+)(?:\[(\d+)\])? (-?\d+)$',l)
    o.append((m.group(1),int(m.group(2)) if m.group(2) else 0,int(m.group(3))))
print(len(g),len(o))
# guest idx printed is 0xffffffff for -1
g=[(n,(0 if i==4294967295 else i),v) for n,i,v in g]
c=0
for i,(a,b) in enumerate(zip(g,o)):
    if a!=b:
        print(i,'guest',a,'oracle',b); c+=1
        if c>25:break
