#!/bin/bash
# lr_run.sh NAME [maxinstr]: run build/lr-NAME.elf; prints total steps, tics, disk
cd /Users/jhome/qwenos-work/wt-lowres
SYMELF=repo2/build/lr-$1/doomd.elf repo2/build/rv32_fast repo2/build/lr-$1.elf engine/DMC100-Doom/build/sw/nor/E1.img 100 108 base/lr-$1.bin ${2:-3000000000} 2>&1 | grep -aE "TICS|DISK|GAMETICS|LEVEL|steps|FAULT|DONE|PANIC"
