#!/bin/bash
# tools/mkdemo.sh [PRESET] : the merged E1M1 demo build (make demo-elf).
#   PRESET: full (default; 15 of 35 tics drawn, 160x200) | balanced | max | none (draw every tic, no skip)
#   env: TICS (game tics to run, default 350)  CHUNKROM=0 (no chunk ROM: disk served through the mailbox)
#        BUDGET (chunk window bytes, default 0x3f000-0x29000)  DMC (engine tree, default ../engine/DMC100-Doom)
# Output (build/demo/): qwenos-e1m1.elf  the merged image (kernel + apps + /bin/doomd, mode 2 scripted E1M1)
#   with CHUNKROM=1 also: crx-plan.bin (rv32_fast CRXPLAN= plan), crx-plan.json (model driver --rom-plan),
#   reqlog.bin, and the verification run: "CRX chunk a-b reqs=N" lines must all say reqs=0.
# Needs the E1 NOR image (default $DMC/build/sw/nor/E1.img, IMG=...).
set -e
if [ "${1:-}" = live ]; then shift; exec "$(dirname "$0")/mkdemo_live.sh" "$@"; fi
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
P=${1:-full}; [ "$P" = none ] && P="-DQ_RN=1 -DQ_RD=1"
export DMC=${DMC:-$ROOT/../engine/DMC100-Doom}
IMG=${IMG:-$DMC/build/sw/nor/E1.img}
OUT=build/demo; mkdir -p $OUT
cc -O2 -o build/rv32_fast tools/rv32_fast.c
make -s build/kernel-doomd.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf >/dev/null
[ "${CHUNKROM:-1}" = 1 ] && export CHUNKROM=1 || unset CHUNKROM
export TICS=${TICS:-350}
ports/doomdmc/lowres.sh demo "$P" >/dev/null
cp build/lr-demo.elf $OUT/qwenos-e1m1.elf
echo "image: $OUT/qwenos-e1m1.elf  (mailboxes: input 0x154, disk 0x15c, fb 0x270)"
rm -f $OUT/crx-plan.bin
symhex() { readelf -sW build/kernel-doomd.elf | awk -v n=$1 '$8==n{print $2}' | sed 's/^0*//'; }
MB="$(symhex qos_input_mailbox) $(symhex qos_disk_mailbox)"
SYM=build/lr-demo/doomd.elf,build/kernel-doomd.elf
echo "dry run (host serves disk) ..."
REQLOG=$OUT/reqlog.bin REQPROF=1 TICLIST=1 SYMELF=$SYM build/rv32_fast $OUT/qwenos-e1m1.elf $IMG $MB $OUT/dry.bin 4000000000 2>&1 | grep -aE "^(GAMETICS|DISK|TICS|steps)" | sed 's/^/  /'
if [ -n "$CHUNKROM" ]; then
  python3 tools/chunkrom.py $OUT/reqlog.bin $IMG --greedy ${BUDGET:+--budget $BUDGET} --out $OUT/crx-plan.bin --json $OUT/crx-plan.json | tail -8
  echo "verification run with the chunk ROM (CRXPLAN) ..."
  CRXPLAN=$OUT/crx-plan.bin CRXBASE=29000 TICLIST=1 SYMELF=$SYM build/rv32_fast $OUT/qwenos-e1m1.elf $IMG $MB $OUT/crx.bin 4000000000 2>&1 | grep -aE "^(CRX|GAMETICS|DISK|TICS|steps)" | sed 's/^/  /'
fi
