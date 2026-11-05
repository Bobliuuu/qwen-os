#!/bin/bash
# One-command live QwenOS terminal:   tools/qwenos_live.sh [--auto] [--fps N] [--keys sched.txt] [--wad W] [--disk E1.img] [--elf X] [--model]
#   (or `make live`, which also builds everything and fetches the engine/Freedoom on first use)
# Tier T0 (default): the guest RV32IM image runs on the host emulator tools/rv32_fast. The host (rv32_fast -L) is only
#   a keyboard, a block device and a display: banner/prompt/echo/ls/`run /bin/doomd` and DOOM itself are all guest instructions.
# Tier T2 (--model): same flow through the real Qwen model (needs a GPU box); this script only PRINTS the command.
# Type  doom  or  run /bin/doomd  at the prompt.  Quit: Ctrl-]  (or Ctrl-C), handled by the host.  Arrow keys = w/s/d/a.
#   --auto   type a short shell tour (help, ls, cat, echo >, cat) and then `run /bin/doomd` for you, then hand the keyboard over
#   --keys   extra key schedule (tools/keysched.py format)
set -e
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$HERE/..
ELF=${ELF:-$REPO/build/qwenos-live-doomdmc-m3.elf}
KELF=${KELF:-$REPO/build/kernel-live.elf}
DMC=${DMC:-$REPO/.deps/engine/DMC100-Doom}
DISK=${DISK:-$DMC/build/sw/nor/E1.img}
WAD=${WAD:-}
FPS=35; KEYS=; AUTO=0; MODEL=0
while [ $# -gt 0 ]; do case $1 in
  --auto) AUTO=1;; --model) MODEL=1;; --fps) FPS=$2; shift;; --keys) KEYS=$2; shift;; --wad) WAD=$2; shift;; --disk) DISK=$2; shift;; --elf) ELF=$2; shift;;
  -h|--help) sed -n 2,11p "$0"; exit 0;;
  *) echo "unknown option $1" >&2; exit 2;; esac; shift; done
if [ $MODEL = 1 ]; then cat <<'TXT'
QwenOS live, tier T2 (REAL MODEL): NOT run by this script. Needs a GPU box with the Qwen3.5 checkpoint + qwenputer:
  CHUNKROM=1 make demo-live                      # typed-flow image with the chunk ROM (build/demo/qwenos-live-e1m1.elf)
  python3 tools/model_doom_qwen.py --help         # driver: the model executes every guest instruction; host = keys/disk/display
See docs/LIVE_DEMO.md ("Real model path"). The typed `run /bin/doomd` flow has NOT been model-verified yet.
TXT
  exit 0; fi
[ -f "$DISK" ] || { echo "no disk image $DISK - run: tools/fetch_engine.sh" >&2; exit 1; }
[ -x "$REPO/build/rv32_fast" ] || { mkdir -p "$REPO/build"; cc -O2 -o "$REPO/build/rv32_fast" "$REPO/tools/rv32_fast.c"; }
if [ ! -f "$ELF" ]; then
  [ -f "$KELF" ] || make -C "$REPO" build/kernel-live.elf build/shell-live.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf >/dev/null
  DMC=$DMC OS=live "$REPO/ports/doomdmc/mkmode.sh" 3 >/dev/null
fi
if [ -z "$WAD" ]; then for w in "$REPO/.deps/wads/freedoom1.wad"; do [ -f "$w" ] && WAD=$w; done; fi
sym() { nm "$KELF" | awk -v s="$1" '$3==s{print $1}'; }
T=$(mktemp -t qoskeys.XXXXXX); trap 'rm -f "$T"' EXIT
if [ $AUTO = 1 ]; then
  python3 -I -c 'import sys;sys.path.insert(0,sys.argv[1]);import keysched;print(keysched.type_lines("help\nls\ncat /README\necho hello qwenos > /tmp/note\ncat /tmp/note\nrun /bin/doomd\n"),end="")' "$HERE" > "$T"
fi
[ -n "$KEYS" ] && cat "$KEYS" >> "$T"
if [ -t 2 ]; then
cat >&2 <<TXT
=== QwenOS live | tier T0: guest RV32IM on the HOST EMULATOR (build/rv32_fast), not the model ===
 host = keyboard + disk blocks + display only; shell, kernel and DOOM run as guest instructions
 type: help, ls, cat /README, ... then  doom  (= run /bin/doomd).  Quit: Ctrl-]   (T2 real model: tools/qwenos_live.sh --model)
TXT
sleep 1
fi
exec "$REPO/build/rv32_fast" -L -K "$T" -W "$(sym qos_key_park)" -B "$(sym qos_framebuffer)" -R "$(sym qos_kv)" -S "$FPS" ${WAD:+-A "$WAD"} \
  "$ELF" "$DISK" "$(sym qos_input_mailbox)" "$(sym qos_disk_mailbox)" /dev/null 0
