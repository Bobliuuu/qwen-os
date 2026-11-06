#!/bin/bash
# vbuild.sh  -> builds verify elf (Q_DUMP_ALL) at wt-perf/base/$1.elf from current wt-perf tree
set -e
cd /Users/jhome/qwenos-work/wt-perf/repo2
export DMC=/Users/jhome/qwenos-work/wt-perf/engine/DMC100-Doom
export DOOMD_MODE=${MODE:-1}
FORCE=1 EXTRA_CF=-DQ_DUMP_ALL ports/doomdmc/build.sh build/doomdmc-v >/dev/null
python3 tools/merge_elf.py ../base/$1.elf build/kernel-doomd.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf build/doomdmc-v/doomd.elf >/dev/null
