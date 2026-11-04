#!/bin/bash
# verify.sh NAME [maxinstr]: build verify elf, run, hash frames, compare with base/v0.h (original)
cd <WORKDIR>/wt-perf
./vbuild.sh $1
repo2/build/rv32_fast base/$1.elf engine/DMC100-Doom/build/sw/nor/E1.img 100 108 base/$1.bin ${2:-1500000000} 2>&1 | head -1
python3 fh.py base/$1.bin base/$1.h
python3 - $1 <<'P'
import sys
a=open('base/v0.h').read().split(); b=open('base/%s.h'%sys.argv[1]).read().split()
n=min(len(a),len(b))
# drop leading title frames? compare aligned from the first game frame found in both (common prefix check)
ok=a[:n]==b[:n]
print('orig unique',len(a),'new unique',len(b),'compared',n,'IDENTICAL' if ok else 'DIFFERENT')
if not ok:
    for i in range(n):
        if a[i]!=b[i]: print('first diff at unique frame',i);break
P
