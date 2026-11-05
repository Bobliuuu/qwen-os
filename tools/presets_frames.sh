#!/bin/bash
# Run the d-* dump builds and decode one frame (default 40) of each to build/pm/png/NAME.png (SCALE 1 = 320x240)
cd "$(dirname "$0")/.."
export DMC=${DMC:-$PWD/../engine/DMC100-Doom}
IMG=$DMC/build/sw/nor/E1.img; WAD=${WAD:-$DMC/build/sw/wad/freedoom1.wad}
WAD=$HOME/qwenos-work/wads/freedoom1.wad
FR=${FR:-40}
mkdir -p build/pm/png
for e in build/lr-d-*-dump.elf; do
  n=${e#build/lr-d-}; n=${n%-dump.elf}
  [ -n "$ONLY" ] && [ "$n" != "$ONLY" ] && continue
  ( build/rv32_fast $e $IMG 154 15c build/pm/d-$n.bin 4000000000 >/dev/null 2>&1
    python3 tools/lowres_frames.py build/pm/d-$n.bin $WAD build/pm/png/$n 2 ${FR} >/dev/null 2>&1 ) &
done
wait
ls build/pm/png
