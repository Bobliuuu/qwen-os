#!/bin/bash
# run.sh ELF symelf [maxinstr] -> tic stats
cd /Users/jhome/qwenos-work/wt-perf
SYMELF=$2 repo2/build/rv32_fast $1 engine/DMC100-Doom/build/sw/nor/E1.img 100 108 base/r.bin ${3:-600000000} 2>&1 | grep -E "TICS|DISK|GAMETICS|LEVEL|steps|FAULT"
