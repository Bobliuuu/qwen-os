#!/bin/bash
# tools/mkdemo_live.sh [PRESET] : the TYPED-FLOW build (make demo-live): interactive-shell kernel + /bin/doomd mode 3
# (E1M1, player driven only by keys from the keyboard mailbox) with the frame-skip preset.
#   cold boot -> prompt parks at qos_key_park -> typed `run /bin/doomd` -> E1M1 -> keys.
#   PRESET full (default) | balanced | max | none.   env: CHUNKROM=1 reserves the chunk window, builds the plan from a
#   scheduled dry run and verifies it (default 0: the host serves disk normally, as the live terminal does).
# Output build/demo/qwenos-live-e1m1.elf ; run it interactively with tools/qwenos_live.sh, or scripted: tools/os_demo.sh
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
P=${1:-full}
case $P in full) F="-DQ_DUMP_COMPACT -DQ_RN=15 -DQ_RD=35";; balanced) F="-DQ_DUMP_COMPACT -DQ_RN=15 -DQ_RD=35 -DQ_VTOP=40 -DQ_VBOT=200 -DQ_DUMP_ROW2";;
  max) F="-DQ_DUMP_COMPACT -DQ_RN=15 -DQ_RD=35 -DQ_DETAIL=2 -DQ_XTVASH=2 -DQ_VTOP=40 -DQ_VBOT=200 -DQ_DUMP_ROW2";; none) F="";; *) F=$P;; esac
export DMC=${DMC:-$ROOT/../engine/DMC100-Doom}; IMG=${IMG:-$DMC/build/sw/nor/E1.img}
OUT=build/demo; mkdir -p $OUT
cc -O2 -o build/rv32_fast tools/rv32_fast.c
make -s build/kernel-live.elf build/shell-live.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf >/dev/null
CRX=0x29000
if [ "${CHUNKROM:-0}" = 1 ]; then export NOBAKE=1 LDX="--defsym=Q_CRX_BASE_LD=$CRX"; F="$F -DQ_CHUNKROM -DQ_CRX_BASE=${CRX}u"; else export NOBAKE=${NOBAKE-1}; fi
OS=live MODE_CF="$F" ports/doomdmc/mkmode.sh 3 >/dev/null
cp build/qwenos-live-doomdmc-m3.elf $OUT/qwenos-live-e1m1.elf
echo "image: $OUT/qwenos-live-e1m1.elf"
if [ "${CHUNKROM:-0}" = 1 ]; then
  sym() { readelf -sW build/kernel-live.elf | awk -v n=$1 '$8==n{print $2}' | sed 's/^0*//'; }
  { for c in r u n space / b i n / d o o m d '\n'; do echo "shell_ready $c"; done
    f=2; for k in w w w w d d w w f f e a a s s w w f e; do echo "frame $f $k"; f=$((f+2)); done; } > $OUT/live-schedule.txt
  A=(-W "0x$(sym qos_key_park)" -F ${FRAMES:-150} -K $OUT/live-schedule.txt $OUT/qwenos-live-e1m1.elf $IMG $(sym qos_input_mailbox) $(sym qos_disk_mailbox))
  REQLOG=$OUT/live-reqlog.bin build/rv32_fast "${A[@]}" $OUT/live-dry.bin 4000000000 2>&1 | grep -aE "^(steps)" | sed 's/^/  dry /'
  python3 tools/chunkrom.py $OUT/live-reqlog.bin $IMG --greedy --out $OUT/live-crx-plan.bin --json $OUT/live-crx-plan.json | tail -3
  CRXPLAN=$OUT/live-crx-plan.bin CRXBASE=29000 build/rv32_fast "${A[@]}" $OUT/live-crx.bin 4000000000 2>&1 | grep -aE "^(CRX|DISK|steps)" | sed 's/^/  /'
fi
