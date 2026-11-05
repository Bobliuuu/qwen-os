#!/bin/bash
# doomd_regress.sh: correctness + cost regression suite of the real DMC100 DOOM (/bin/doomd) on RV32IM.
#
#   tools/doomd_regress.sh            build, run, compare against tests/golden, print stats
#   tools/doomd_regress.sh --update   adopt the current state/frame/perf results as the new goldens
#   options: --no-build (reuse build/regress/*.elf)  --clean (force rebuild)  --fail-perf
#            --tics1 N (DEMO1 game frames, default 260)  --tics2 N (E1M1 scripted, default 100)
#   env: DMC (DMC100-Doom checkout), IMG (NOR image), ORIG_H (frame-hash list of the ORIGINAL
#        pre-optimisation build, default <root>/../base/v0long.h when present), REGRESS_OUT
#
# What is checked (any difference exits 1):
#   state  per-tic lockstep game-state hash (players, sectors, all mobjs; DMC100 tests/lockstep/hash.c,
#          rndindex excluded) for DEMO1 (mode 1) and the E1M1 scripted run (mode 2): identical to golden
#   frames per-frame picture hash (320x240 canvas + palette) of both runs identical to golden, and
#          of a build WITHOUT the hash code (so the hash scratch cannot hide a rendering bug)
#   orig   DEMO1 frames identical to the original build's (ORIG_H), when the file is there
#   tics   the production build (no dump, no hash) runs the same frame/tic sequence
# Reported: instr/tic (mean, median, p90, max) and disk requests/tic of the production build; a
# regression > 5% instr or > 10% requests against tests/golden/perf_baseline.txt warns (--fail-perf fails).
# The goldens come from the build whose DEMO1 frames were verified identical to the original build
# (see tests/golden/README.txt); --update must only be used after that check (ORIG_H).
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
GOLD=$ROOT/tests/golden
OUT=${REGRESS_OUT:-$ROOT/build/regress}
export DMC=${DMC:-$ROOT/.deps/engine/DMC100-Doom}
IMG=${IMG:-$DMC/build/sw/nor/E1.img}
[ -z "${ORIG_H:-}" ] && [ -f "$ROOT/../base/v0long.h" ] && ORIG_H=$ROOT/../base/v0long.h
UPDATE= NOBUILD= CLEAN= FAILPERF= T1=260 T2=100
while [ $# -gt 0 ]; do case $1 in
  --update) UPDATE=1;; --no-build) NOBUILD=1;; --clean) CLEAN=1;; --fail-perf) FAILPERF=--fail-perf;;
  --tics1) T1=$2; shift;; --tics2) T2=$2; shift;; -h|--help) sed -n 2,26p "$0"; exit 0;;
  *) echo "unknown option $1"; exit 2;; esac; shift; done
mkdir -p "$OUT" "$GOLD"
RC=0; fail() { echo "$@"; RC=1; }
[ -f "$IMG" ] || { echo "NOR image $IMG missing (set IMG/DMC)"; exit 2; }

# ---- tools
cc -O2 -o "$ROOT/build/rv32_fast" "$ROOT/tools/rv32_fast.c" || exit 2
FAST=$ROOT/build/rv32_fast
for e in kernel-doomd shell paint raycast asset doom; do
  [ -f "$ROOT/build/$e.elf" ] || make -C "$ROOT" build/$e.elf >/dev/null || { echo "cannot build $e.elf"; exit 2; }
done

# ---- builds: NAME MODE FRAMES "env..."   (check = hash + dump, frm = dump only, prod = neither)
build() {
  local name=$1 mode=$2 frames=$3; shift 3
  local d=$OUT/$name flags="$mode $frames $* $DMC"
  [ -n "$NOBUILD" ] && return 0
  local force=; { [ -n "$CLEAN" ] || [ "$(cat $d/flags 2>/dev/null)" != "$flags" ]; } && force=1
  mkdir -p "$d"
  ( env "$@" DOOMD_MODE=$mode FORCE=$force EXTRA_CF="-DDOOMD_FRAMES=$frames $EXTRA" "$ROOT/ports/doomdmc/build.sh" "$d" >/dev/null 2>"$d/build.log" &&
    python3 "$ROOT/tools/merge_elf.py" "$OUT/$name.elf" "$ROOT/build/kernel-doomd.elf" "$ROOT/build/shell.elf" "$ROOT/build/paint.elf" \
       "$ROOT/build/raycast.elf" "$ROOT/build/asset.elf" "$ROOT/build/doom.elf" "$d/doomd.elf" >/dev/null &&
    echo "$flags" > "$d/flags" ) || { echo "BUILD FAILED: $name (see $d/build.log)"; return 1; }
}
echo "== building (parallel)"
EXTRA="-DQ_DUMP_ALL" build chk1 1 $T1 QHASH=1 & P1=$!
EXTRA="-DQ_DUMP_ALL" build frm1 1 $T1 X=1 & P2=$!
EXTRA="-DQ_DUMP_ALL" build chk2 2 $T2 QHASH=1 & P3=$!
EXTRA="" build prod1 1 $T1 X=1 & P4=$!
EXTRA="" build prod2 2 $T2 X=1 & P5=$!
for p in $P1 $P2 $P3 $P4 $P5; do wait $p || RC=1; done
[ $RC -ne 0 ] && exit 1

# ---- runs
run() { # name elf -> $OUT/name.bin, $OUT/name.log (stderr of the twin)
  SYMELF=$OUT/${3:-$1}/doomd.elf "$FAST" "$OUT/$1.elf" "$IMG" 154 15c "$OUT/$1.bin" 20000000000 >"$OUT/$1.log" 2>&1
  local rc=$?
  [ $rc -eq 0 ] || { echo "FAIL $1: guest did not finish cleanly (rv32_fast exit $rc: 99 = DOOMD PANIC, see $OUT/$1.log and the end of $OUT/$1.bin)"; return 1; }
}
echo "== running"
PIDS=; for n in chk1 frm1 chk2 prod1 prod2; do run $n & PIDS="$PIDS $!"; done
for p in $PIDS; do wait $p || RC=1; done
[ $RC -ne 0 ] && exit 1

# ---- compare
echo "== comparing"
H=$ROOT/tools/doomd_hashes.py; C=$ROOT/tools/doomd_regress_cmp.py
python3 $H "$OUT/chk1.bin" "$OUT/m1.states" "$OUT/m1.frames" >/dev/null
python3 $H "$OUT/frm1.bin" /dev/null "$OUT/m1.nohash.frames" >/dev/null
python3 $H "$OUT/chk2.bin" "$OUT/m2.states" "$OUT/m2.frames" >/dev/null
if [ -n "$UPDATE" ]; then
  cp "$OUT/m1.states" "$GOLD/doomd_m1_states.txt"; cp "$OUT/m1.frames" "$GOLD/doomd_m1_frames.txt"
  cp "$OUT/m2.states" "$GOLD/doomd_m2_states.txt"; cp "$OUT/m2.frames" "$GOLD/doomd_m2_frames.txt"
  python3 - "$OUT" "$ROOT/tools" > "$GOLD/perf_baseline.txt" <<'PY'
import sys
sys.path.insert(0, sys.argv[2])
import doomd_regress_cmp as c
for m in (1, 2):
    r = c.parse_stats('%s/prod%d.log' % (sys.argv[1], m))
    print('m%d %d %d %d' % (m, r['mean'], r['req_per_tic'], r['n']))
PY
  echo "goldens updated in $GOLD"
fi
python3 $C diff m1-states "$GOLD/doomd_m1_states.txt" "$OUT/m1.states" || RC=1
python3 $C diff m1-frames "$GOLD/doomd_m1_frames.txt" "$OUT/m1.frames" || RC=1
python3 $C diff m1-frames-nohash "$GOLD/doomd_m1_frames.txt" "$OUT/m1.nohash.frames" || RC=1
python3 $C diff m2-states "$GOLD/doomd_m2_states.txt" "$OUT/m2.states" || RC=1
python3 $C diff m2-frames "$GOLD/doomd_m2_frames.txt" "$OUT/m2.frames" || RC=1
[ -n "${ORIG_H:-}" ] && { python3 $C orig m1-vs-original "$ORIG_H" "$OUT/m1.frames" || RC=1; }
python3 $C tics m1-prod-vs-check "$OUT/prod1.bin" "$OUT/chk1.bin" || RC=1
python3 $C tics m2-prod-vs-check "$OUT/prod2.bin" "$OUT/chk2.bin" || RC=1
echo "== cost (production build, E1.img, instr per game tic; disk requests per tic)"
python3 $C stats m1 "$OUT/prod1.log" "$GOLD/perf_baseline.txt" $FAILPERF || RC=1
python3 $C stats m2 "$OUT/prod2.log" "$GOLD/perf_baseline.txt" $FAILPERF || RC=1
[ $RC -eq 0 ] && echo "PASS doomd_regress" || echo "FAIL doomd_regress"
exit $RC
