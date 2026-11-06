#!/bin/bash
# build.sh : full perf build -> wt-perf/base/new.elf
set -e
cd /Users/jhome/qwenos-work/wt-perf/repo2
export DMC=/Users/jhome/qwenos-work/wt-perf/engine/DMC100-Doom
export DOOMD_MODE=${MODE:-1}
cc -O2 -o build/rv32_fast tools/rv32_fast.c
make build/kernel-doomd.elf >/dev/null 2>&1 || true
FORCE=1 ports/doomdmc/build.sh build/doomdmc >/dev/null
cp build/doomdmc/doomd.elf build/doomdmc.elf
python3 tools/merge_elf.py build/qwenos-doomdmc.elf build/kernel-doomd.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf build/doomdmc.elf >/dev/null
cp build/qwenos-doomdmc.elf ../base/new.elf
readelf -SW build/doomdmc/doomd.elf | grep -E " \.(text|rodata) "
readelf -SW build/kernel-doomd.elf | grep -E " \.text"
