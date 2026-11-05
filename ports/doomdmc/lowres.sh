#!/bin/bash
# Build one lowres/frame-skip variant of /bin/doomd (mode 2, E1M1 scripted run) as its own image:
#   ports/doomdmc/lowres.sh NAME "-DQ_... -DQ_..." [dump]   ->  build/lr-NAME[-dump].elf
# Knobs (see doomd_main.c, doomd_main/qlcd/r_frame/r_main in the engine): Q_DETAIL (0/1/2), Q_XTVASH=2 with
# Q_DETAIL=2, Q_VTOP/Q_VBOT (letterbox rows), Q_NOBAR, Q_FIXEDLIGHT=n, Q_SOLID, Q_STRIPW=w, Q_RN/Q_RD (frame
# skip), Q_DUMP_COMPACT (host replicates columns in the dump). dump => Q_DUMP_ALL (every frame over PUTC).
set -e
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$HERE/../..
N=${1:?name}; F=${2:-}; D=${3:-}
# named presets (second argument may be a preset name instead of flags); all: 15 rendered frames per 35 game tics
#   full      160 columns x 200 rows, as the perf build, only frame skipping
#   balanced  full + rows 40..199 only (ceiling letterbox) + dump sends every 2nd row
#   max       80 columns (x4 on the host) + rows 40..199 + dump rows halved + frame skipping
#   lite      160 columns, rows 40..199 only, no status bar, no light diminishing (15 fps)
#   fast      lite with 80 columns (x2 on the host: max + no status bar + no light diminishing) (15 fps)
SK="-DQ_DUMP_COMPACT -DQ_RN=15 -DQ_RD=35"
case "$F" in
  full)     F="$SK";;
  balanced) F="$SK -DQ_VTOP=40 -DQ_VBOT=200 -DQ_DUMP_ROW2";;
  max)      F="$SK -DQ_DETAIL=2 -DQ_XTVASH=2 -DQ_VTOP=40 -DQ_VBOT=200 -DQ_DUMP_ROW2";;
  # TRADEOFF presets (visual quality is reduced, the game simulation still runs every tic; see docs/research/PRESETS.md)
  fast)     F="$SK -DQ_DETAIL=2 -DQ_XTVASH=2 -DQ_VTOP=40 -DQ_VBOT=200 -DQ_NOBAR -DQ_FIXEDLIGHT=0 -DQ_DUMP_ROW2";;
  lite)     F="$SK -DQ_VTOP=40 -DQ_VBOT=200 -DQ_NOBAR -DQ_FIXEDLIGHT=0 -DQ_DUMP_ROW2";;
esac
T=$N; [ -n "$D" ] && T=$N-dump
OUT=$REPO/build/lr-$T
mkdir -p $OUT
# CHUNKROM=1: guest reads disk extents from a host-filled data-ROM window (ports/doomdmc/qplat.c crx_read,
# tools/chunkrom.py); the window [Q_CRX_BASE, 0x3f000) is reserved by the linker, the E1M6 bake is dropped.
CRX=${Q_CRX_BASE:-0x29000}
if [ -n "$CHUNKROM" ]; then export NOBAKE=1 LDX="$LDX --defsym=Q_CRX_BASE_LD=$CRX"; F="$F -DQ_CHUNKROM -DQ_CRX_BASE=${CRX}u"; fi
X="-DDOOMD_TICS=${TICS:-350} $F"; [ -n "$D" ] && X="$X -DQ_DUMP_ALL"
FORCE=1 DOOMD_MODE=2 EXTRA_CF="$X $EXTRA_CF" $HERE/build.sh $OUT >/dev/null
cd $REPO
python3 tools/merge_elf.py build/lr-$T.elf build/kernel-doomd.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf $OUT/doomd.elf | tail -1
