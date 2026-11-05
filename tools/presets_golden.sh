#!/bin/bash
# tools/presets_golden.sh [--update] [PRESET...]   (default presets: full lite fast)
# Golden check of the TRADEOFF presets (E1M1 mode 2, 100 game tics, QHASH state hash + full frame dump):
#   states  per-tic lockstep game-state hash must equal tests/golden/presets/full_states.txt (the FULL lowres build,
#           same 15-of-35 draw schedule; note: not the regress m2 golden, whose build draws every tic)
#           (proves the simulation is untouched: only rendering was reduced)
#   frames  per-frame picture hashes of the preset == tests/golden/presets/<name>_frames.txt
# --update adopts the frame hashes of the current build as the preset golden.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
export DMC=${DMC:-$ROOT/../engine/DMC100-Doom}; IMG=${IMG:-$DMC/build/sw/nor/E1.img}
UPD=; [ "${1:-}" = --update ] && { UPD=1; shift; }
PRESETS=${*:-full lite fast}
GOLD=$ROOT/tests/golden; mkdir -p $GOLD/presets build/pg
[ -x build/rv32_fast ] || cc -O2 -o build/rv32_fast tools/rv32_fast.c
RC=0
for P in $PRESETS; do
  QHASH=1 TICS=100 ports/doomdmc/lowres.sh g-$P $P dump >/dev/null || { echo "BUILD FAILED $P"; RC=1; continue; }
  build/rv32_fast build/lr-g-$P-dump.elf $IMG 154 15c build/pg/$P.bin 20000000000 >build/pg/$P.log 2>&1
  python3 tools/doomd_hashes.py build/pg/$P.bin build/pg/$P.states build/pg/$P.frames >/dev/null
  [ -n "$UPD" ] && [ $P = full ] && cp build/pg/full.states $GOLD/presets/full_states.txt
  if python3 tools/doomd_regress_cmp.py diff $P-states $GOLD/presets/full_states.txt build/pg/$P.states; then :; else RC=1; fi
  if [ -n "$UPD" ]; then cp build/pg/$P.frames $GOLD/presets/${P}_frames.txt; echo "updated $P golden ($(wc -l < build/pg/$P.frames) frames)"
  else python3 tools/doomd_regress_cmp.py diff $P-frames $GOLD/presets/${P}_frames.txt build/pg/$P.frames || RC=1; fi
done
exit $RC
