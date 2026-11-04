#!/bin/bash
# mk.sh TAG [mode] [frames] : build repo tree into build/doomdmc-TAG and merged elf build/q-TAG.elf
W=<WORKDIR>/wt-merge; cd $W/repo
T=$1; export DOOMD_MODE=${2:-2}
FORCE=1 EXTRA_CF="-DDOOMD_FRAMES=${3:-350} $EXTRA" ports/doomdmc/build.sh build/doomdmc-$T | grep -E "text|rodata|\.data|\.bss" 
python3 tools/merge_elf.py build/q-$T.elf build/kernel-doomd.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf build/doomdmc-$T/doomd.elf | tail -1
