#!/bin/bash
# One-command live QwenOS terminal:  tools/qwenos_live.sh [--auto] [--fps N] [--keys sched.txt] [--wad freedoom1.wad] [--disk E1.img]
# The host (tools/rv32_fast -L) is only a keyboard, a block device and a display: boot banner/prompt/echo/ls/
# `run /bin/doomd` and DOOM itself all run as guest RV32 instructions. Type  run /bin/doomd  <Enter>.
# Quit: Ctrl-]  (or Ctrl-C) - handled by the host, never sent to the guest.  Arrow keys = w/s/d/a.
#   --auto   type "run /bin/doomd" for you (scripted keys), then hand the keyboard over
#   --keys   extra key schedule (tools/keysched.py format), replayable in non-live runs too
set -e
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$HERE/..
ELF=${ELF:-$REPO/build/qwenos-live-doomdmc-m3.elf}
KELF=${KELF:-$REPO/build/kernel-live.elf}
DISK=${DISK:-$REPO/../engine/DMC100-Doom/build/sw/nor/E1.img}
WAD=${WAD:-}
for w in "$REPO/../wads/freedoom1.wad" "$REPO/../../wads/freedoom1.wad" "$HOME/qwenos-work/wads/freedoom1.wad"; do [ -z "$WAD" ] && [ -f "$w" ] && WAD=$w; done
FPS=35; KEYS=; AUTO=0
while [ $# -gt 0 ]; do case $1 in
  --auto) AUTO=1;; --fps) FPS=$2; shift;; --keys) KEYS=$2; shift;; --wad) WAD=$2; shift;; --disk) DISK=$2; shift;; --elf) ELF=$2; shift;;
  *) echo "unknown option $1" >&2; exit 2;; esac; shift; done
[ -x "$REPO/build/rv32_fast" ] || cc -O2 -o "$REPO/build/rv32_fast" "$REPO/tools/rv32_fast.c"
if [ ! -f "$ELF" ]; then
  [ -f "$KELF" ] || make -C "$REPO" build/kernel-live.elf build/shell-live.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf >/dev/null
  OS=live "$REPO/ports/doomdmc/mkmode.sh" 3 >/dev/null
fi
sym() { nm "$KELF" | awk -v s="$1" '$3==s{print $1}'; }
T=$(mktemp -t qoskeys.XXXXXX); trap 'rm -f "$T"' EXIT
if [ $AUTO = 1 ]; then
  for c in r u n space / b i n / d o o m d '\n'; do echo "shell_ready $c"; done > "$T"
fi
[ -n "$KEYS" ] && cat "$KEYS" >> "$T"
exec "$REPO/build/rv32_fast" -L -K "$T" -W "$(sym qos_key_park)" -B "$(sym qos_framebuffer)" -R "$(sym qos_kv)" -S "$FPS" ${WAD:+-A "$WAD"} \
  "$ELF" "$DISK" "$(sym qos_input_mailbox)" "$(sym qos_disk_mailbox)" /dev/null 0
