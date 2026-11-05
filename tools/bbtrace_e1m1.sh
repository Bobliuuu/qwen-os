#!/bin/bash
# tools/bbtrace_e1m1.sh: trace the real scripted E1M1 demo image (make demo-elf) and write docs/research/BBTRACE.md.
# Needs: make demo-elf done (build/demo/qwenos-e1m1.elf, build/lr-demo/doomd.elf, build/kernel-doomd.elf) and the E1 NOR image
# (default $DMC/build/sw/nor/E1.img). Host emulator only, host-served disk (the dry run of tools/mkdemo.sh).
# env: DMC, IMG, MAXI (default 4000000000 = run to exit), OUTMD, BBOUT
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
export DMC=${DMC:-$ROOT/../engine/DMC100-Doom}
IMG=${IMG:-$DMC/build/sw/nor/E1.img}
ELF=build/demo/qwenos-e1m1.elf
symhex() { readelf -sW build/kernel-doomd.elf | awk -v n=$1 '$8==n{print $2}' | sed 's/^0*//'; }
MB="$(symhex qos_input_mailbox) $(symhex qos_disk_mailbox)"
export BBOUT=${BBOUT:-$ROOT/build/bbtrace.out}
SYMELF=build/lr-demo/doomd.elf,build/kernel-doomd.elf tools/bbtrace $ELF $IMG $MB build/demo/bb.bin ${MAXI:-4000000000} 2>&1 | grep -aE "^(GAMETICS|TICS|steps)"
python3 tools/bbtrace_report.py --elf $ELF --dir $BBOUT --sym build/lr-demo/doomd.elf,build/kernel-doomd.elf --out ${OUTMD:-docs/research/BBTRACE.md} --copy-tics docs/research/bbtrace/tics.tsv \
  --repro "DMC=<DMC100-Doom tree with engine-patches applied> make demo-elf   # build the image, once
DMC=<same tree> tools/bbtrace_e1m1.sh                                        # trace + write this report"
