#!/bin/bash
# usage: prof.sh ELF symelf PHASES(tic numbers) [maxinstr]
cd <WORKDIR>/wt-perf
SYMELF=$2,repo2/build/kernel-doomd.elf PROF=1 PHASES=$3 repo2/build/rv32_fast $1 engine/DMC100-Doom/build/sw/nor/E1.img 100 108 base/prof.bin ${4:-60000000} 2>&1 | grep -v "^frame "
