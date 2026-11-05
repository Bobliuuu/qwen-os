#!/bin/bash
# tools/presets_measure.sh NAME "-DQ_flags|preset" : build one lowres variant, run E1M1 (TICS game tics), print per-tic stats.
#   instr/tic and TOKCOST tokens/tic (mean, median); writes build/pm/NAME.tics (per tic: instr tok).
#   env: TICS (default 350)  DMC (patched engine tree)  IMG
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
N=${1:?name}; F=${2:-}
export DMC=${DMC:-$ROOT/../engine/DMC100-Doom}; IMG=${IMG:-$DMC/build/sw/nor/E1.img}
mkdir -p build/pm
[ -x build/rv32_fast ] || cc -O2 -o build/rv32_fast tools/rv32_fast.c
TICS=${TICS:-350} ports/doomdmc/lowres.sh pm-$N "$F" >/dev/null
sym() { readelf -sW build/kernel-doomd.elf | awk -v n=$1 '$8==n{print $2}' | sed 's/^0*//'; }
SYMELF=build/lr-pm-$N/doomd.elf,build/kernel-doomd.elf TOKCOST=1 TICLIST=1 build/rv32_fast build/lr-pm-$N.elf $IMG $(sym qos_input_mailbox) $(sym qos_disk_mailbox) build/pm/$N.out 4000000000 2>build/pm/$N.log >/dev/null || true
grep -a "^tic " build/pm/$N.log | awk '{print $6, $8}' > build/pm/$N.tics
python3 - "$N" <<'P'
import sys,statistics as st
n=sys.argv[1]; r=[tuple(map(int,l.split())) for l in open(f'build/pm/{n}.tics')]
i=[a for a,b in r]; t=[b for a,b in r]
print(f"{n}: tics={len(r)} instr/tic mean={st.mean(i):.0f} median={st.median(i):.0f} | tok/tic mean={st.mean(t):.0f} median={st.median(t):.0f} | total instr={sum(i)} tok={sum(t)}")
P
