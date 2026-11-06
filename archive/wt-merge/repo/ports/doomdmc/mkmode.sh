#!/bin/bash
# Build a /bin/doomd run-mode variant as its own full image, without touching build/doomdmc.elf.
#   ports/doomdmc/mkmode.sh MODE [FRAMES [DUMP]]  ->  build/qwenos-doomdmc-m<MODE>[f<FRAMES>].elf
# MODE 1: DEMO1 straight away; MODE 2: E1M1 start with scripted input; MODE 3: E1M1 start driven only
# by keyboard-mailbox keys; FRAMES>0: exit after that many game frames (marker DOOMD_FRAMES_DONE).
# MODE_CF="-D..." adds compiler flags (e.g. -DQ_RN=15 -DQ_RD=35, -DQ_CHUNKROM); LDX passes linker flags; objects are always rebuilt (FORCE=1).
# See doomd_main.c.  OS=live merges with the interactive shell kernel (kernel-live + shell-live) and
# names the image build/qwenos-live-doomdmc-<T>.elf; default OS=boot is the boot-script kernel.
set -e
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$HERE/../..
M=${1:?mode}; F=${2:-0}; D=${3:-0}
T=m$M; [ "$F" != 0 ] && T=${T}f$F; [ "$D" != 0 ] && T=${T}d
OS=${OS:-boot}
OUT=$REPO/build/doomdmc-$T
mkdir -p $OUT
# the mode is baked into doomd_main.o only; everything else is shared with the default build
if [ ! -d $OUT/o ]; then mkdir -p $OUT/o; cp -p $REPO/build/doomdmc/o/*.o $OUT/o/ 2>/dev/null || true; fi
rm -f $OUT/o/doomd_main.o $OUT/o/qplat.o
FORCE=${FORCE:-1} DOOMD_MODE=$M DOOMD_DUMP=$D EXTRA_CF="-DDOOMD_FRAMES=$F $MODE_CF" $HERE/build.sh $OUT >/dev/null
cd $REPO
if [ "$OS" = live ]; then
  python3 tools/merge_elf.py build/qwenos-live-doomdmc-$T.elf build/kernel-live.elf build/shell-live.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf $OUT/doomd.elf | tail -1
else
  python3 tools/merge_elf.py build/qwenos-doomdmc-$T.elf build/kernel-doomd.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf $OUT/doomd.elf | tail -1
fi
