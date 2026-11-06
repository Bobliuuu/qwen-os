#!/bin/bash
# tics.sh ELF SYMELF TAG [maxinstr] [image]: run, write out/TAG.log (tic costs) + out/TAG.fb
W=/Users/jhome/qwenos-work/wt-merge
IMG=${5:-$W/engine/DMC100-Doom/build/sw/nor/E1.img}
FBADDR=${FBADDR:-170} FBLOG=$W/out/$3.fb TICLIST=1 REQPROF=1 SYMELF=$2 $W/repo/build/rv32_fast $1 $IMG 54 5c $W/out/$3.bin ${4:-650000000} > $W/out/$3.raw 2>&1
grep -E "^tic|TICS|steps|DISK|REQ|panic|FAULT" $W/out/$3.raw > $W/out/$3.log
python3 - $W/out/$3.log <<'P'
import sys,re
L=open(sys.argv[1]).read().split('\n')
t=[tuple(map(int,m.groups())) for l in L for m in [re.match(r'tic (\d+) at \d+ cost (\d+) req (\d+)',l)] if m]
c=[x[1] for x in t]; r=[x[2] for x in t]
def m(x,a,b): y=x[a:b]; return sum(y)/max(1,len(y))
print('tics',len(c),'instr/tic 0-30 %d  30-300 %d  total(sum tic) %d'%(m(c,0,30),m(c,30,300),sum(c)))
print('req/tic 0-30 %.1f  30-300 %.1f  total %d'%(m(r,0,30),m(r,30,300),sum(r)))
for l in L:
    if l.startswith(('TICS','GAMETICS','DISK','LEVEL','steps','FAULT')): print(l)
P
