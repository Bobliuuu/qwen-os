#!/bin/bash
# Build a /bin/doomd run-mode variant as its own full image, without touching build/doomdmc.elf.
#   ports/doomdmc/mkmode.sh MODE [FRAMES [DUMP]]  ->  build/qwenos-doomdmc-m<MODE>[f<FRAMES>].elf
# MODE 1: DEMO1 straight away; MODE 2: E1M1 start with scripted input; FRAMES>0: exit after that
# many game frames (marker DOOMD_FRAMES_DONE). See doomd_main.c.
set -e
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$HERE/../..
M=${1:?mode}; F=${2:-0}; D=${3:-0}
T=m$M; [ "$F" != 0 ] && T=${T}f$F; [ "$D" != 0 ] && T=${T}d
OUT=$REPO/build/doomdmc-$T
mkdir -p $OUT
# the mode is baked into doomd_main.o only; everything else is shared with the default build
if [ ! -d $OUT/o ]; then mkdir -p $OUT/o; cp -p $REPO/build/doomdmc/o/*.o $OUT/o/ 2>/dev/null || true; fi
rm -f $OUT/o/doomd_main.o $OUT/o/qplat.o $OUT/o/qlcd.o
DOOMD_MODE=$M DOOMD_DUMP=$D EXTRA_CF="-DDOOMD_FRAMES=$F ${XCF}" $HERE/build.sh $OUT >/dev/null
cd $REPO
python3 tools/merge_elf.py build/qwenos-doomdmc-$T.elf build/kernel-doomd.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf $OUT/doomd.elf | tail -1
