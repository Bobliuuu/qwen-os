#!/bin/bash
# Scripted end-to-end QwenOS demo on rv32_fast: cold boot -> shell prompt -> typed `run /bin/doomd` -> E1M1 ->
# simulated keyboard (move/turn/fire/use) while DOOM runs. All keys go through the guest keyboard mailbox
# (schedule file = keysched.py format); the host only types, serves disk blocks and records.
#   tools/os_demo.sh [outdir] [frames]        default build/os_demo, 40 frames
# Writes: schedule.txt, console-measure.bin (guest console bytes), summary.txt (instruction counts),
#         frames/*.png (full 320x240 frames, taken in a SECOND run with 'p' dump keys; the dump costs extra
#         instructions, so the numbers in summary.txt come from the first, dump-free run).
set -e
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$HERE/..
OUT=${1:-$REPO/build/os_demo}; NF=${2:-40}
ELF=${ELF:-$REPO/build/qwenos-live-doomdmc-m3.elf}
KELF=$REPO/build/kernel-live.elf; DOOMELF=${DOOMELF:-$REPO/build/doomdmc-m3/doomd.elf}
DISK=${DISK:-$REPO/../engine/DMC100-Doom/build/sw/nor/E1.img}
if [ -z "$WAD" ]; then for w in "$REPO/../wads/freedoom1.wad" "$REPO/../../wads/freedoom1.wad" "$HOME/qwenos-work/wads/freedoom1.wad"; do [ -f "$w" ] && WAD=$w && break; done; fi
mkdir -p "$OUT/frames"
[ -x "$REPO/build/rv32_fast" ] || cc -O2 -o "$REPO/build/rv32_fast" "$REPO/tools/rv32_fast.c"
if [ ! -f "$ELF" ]; then
  make -C "$REPO" build/kernel-live.elf build/shell-live.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf >/dev/null
  OS=live "$REPO/ports/doomdmc/mkmode.sh" 3 >/dev/null
fi
sym() { nm "$KELF" | awk -v s="$1" '$3==s{print $1}'; }
# --- key schedule: type the command at the prompt, then play. Frame numbers count 0x02 markers since boot.
{
  echo "# typed at the prompt, one key per park of the shell (shell_ready)"
  for c in r u n space / b i n / d o o m d '\n'; do echo "shell_ready $c"; done
  echo "# DOOM: walk forward, turn right, walk, fire, use, turn left, back up (each key = ~4 tics held)"
  f=2; for k in w w w w d d w w f f e a a s s w w f e; do echo "frame $f $k"; f=$((f+2)); done
} > "$OUT/schedule.txt"
COMMON=(-W "$(sym qos_key_park)" -F "$NF")
ARGS=("$ELF" "$DISK" "$(sym qos_input_mailbox)" "$(sym qos_disk_mailbox)")
# --- run A: measurement (no dumps)
SYMELF=$DOOMELF,$KELF WATCH=qos_key_park,qos_takeover_run,doomd_main,P_SetupLevel \
  "$REPO/build/rv32_fast" -v "${COMMON[@]}" -K "$OUT/schedule.txt" "${ARGS[@]}" "$OUT/console-measure.bin" 500000000 2> "$OUT/run-measure.log" || true
python3 - "$OUT" <<'PY'
import re,sys
out=sys.argv[1];log=open(out+'/run-measure.log').read()
keys=[(int(a),int(b),w) for a,b,w in re.findall(r'KEY step=(\d+) key=(\d+) seq=\d+ via (\S+)',log)]
w=dict((n,int(s)) for n,s in re.findall(r'WATCH (\w+) at (\d+)',log))
fr=[int(a) for a in re.findall(r'frame \d+ at (\d+)',log)]
typed=[k for k in keys if k[2]=='shell_ready']
enter=typed[-1][0] if typed else 0
m=re.search(r'steps=(\d+) exit=(\S+) frames=(\d+)',log)
L=[]
def p(s):L.append(s);print(s)
p('QwenOS end-to-end demo (rv32_fast, instructions = guest RV32 instructions; chip tokens ~ 1.35 x instr)')
p('  cold boot -> shell prompt parked at KEY_WAIT : %9d' % w['qos_key_park'])
p('  typing "run /bin/doomd\\n" (%d keys, %d..%d): %9d  (%d per key)' % (len(typed),typed[0][0],enter,enter-w['qos_key_park'],(enter-w['qos_key_park'])//max(1,len(typed))))
p('  Enter -> kernel takeover entry               : %9d' % (w['qos_takeover_run']-enter))
p('  takeover -> doomd_main                       : %9d' % (w['doomd_main']-w['qos_takeover_run']))
p('  doomd init (img, FAT, engine) -> level start : %9d' % (w['P_SetupLevel']-w['doomd_main']))
p('  level load + first E1M1 frame                : %9d' % (fr[0]-w['P_SetupLevel']))
p('  TOTAL cold boot -> first E1M1 frame          : %9d' % fr[0])
p('    of which OS (boot+shell+typing+exec+takeover) : %9d' % w['doomd_main'])
d=[b-a for a,b in zip(fr,fr[1:])]
if d:
  kf=[i for i in range(len(d)) if True]
  p('  per frame (%d frames, %d keys injected in-game): mean %d  min %d  max %d' % (len(d),len(keys)-len(typed),sum(d)//len(d),min(d),max(d)))
p('  run: %s' % m.group(0) if m else '  run: ?')
open(out+'/summary.txt','w').write('\n'.join(L)+'\n')
PY
# --- run B: same flow plus 'p' (serial LCD dump) keys -> full-resolution PNG frames
# (schedule order is strict: 'p' arms the dump of the NEXT frame; 4000 = before doomd's first key poll -> first E1M1 frame)
awk '/^frame (6|14|30) /{print; print "frame " $2 " p"; next} /^frame 2 /{print "4000 p"} {print}' "$OUT/schedule.txt" > "$OUT/schedule-dump.txt"
"$REPO/build/rv32_fast" "${COMMON[@]}" -K "$OUT/schedule-dump.txt" "${ARGS[@]}" "$OUT/console-dump.bin" 500000000 2> "$OUT/run-dump.log" || true
if [ -f "$WAD" ]; then python3 "$REPO/tools/doomd_frames.py" "$OUT/console-dump.bin" "$WAD" "$OUT/frames/frame" 2 | tail -5; else echo "no WAD at $WAD (set WAD=) - skipping PNGs"; fi
echo "outputs in $OUT"
