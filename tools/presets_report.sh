#!/bin/bash
# Final numbers + PNGs for the shipped presets (full lite fast): build/pm/final.txt, build/pm/png/*.png
cd "$(dirname "$0")/.."
export DMC=${DMC:-$PWD/../engine/DMC100-Doom}
rm -rf build/lr-d-*
for n in full lite fast; do (TICS=100 ports/doomdmc/lowres.sh d-$n $n dump >/dev/null) & done; wait
rm -f build/pm/png/*
tools/presets_frames.sh >/dev/null
: > build/pm/final.txt
for n in full lite fast; do tools/presets_measure.sh p_$n $n >> build/pm/final.txt; done
cat build/pm/final.txt
