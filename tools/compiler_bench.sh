#!/bin/bash
# tools/compiler_bench.sh NAME  : build one compiler configuration of /bin/doomd (FULL preset, E1M1 scripted,
# host-served disk) and report host-emulator numbers. Configure through the env knobs of
# ports/doomdmc/build.sh (OPT, EXTRA_CF, INNER_CF, LDX, LDRELAX, RELAXFLAG, ...).
#   prints one line: NAME steps=<dynamic instr, whole run> GAMETICS=<n> text= rodata= data= bss= (bytes) md5=<console md5>
# The console md5 covers the whole frame stream, so equal md5 across configs = identical pictures and tic sequence.
# These are instruction counts of the C twin (tools/rv32_fast.c): host-emulator numbers, NOT Qwen speedups.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
N=${1:?name}
export DMC=${DMC:-$ROOT/../engine/DMC100-Doom}
IMG=${IMG:-$DMC/build/sw/nor/E1.img}
OUT=${BENCH_OUT:-$ROOT/build/bench}; mkdir -p $OUT
# production image = chunk-ROM build (rodata must fit 0x21000..0x29000); the window itself is left empty here, so
# crx_read always misses and the host serves the disk (same code path as the dry run of tools/mkdemo.sh)
if [ "${BENCH_CRX:-1}" = 1 ]; then export CHUNKROM=1; else unset CHUNKROM; fi
export TICS=${TICS:-350}
ports/doomdmc/lowres.sh bench-$N full >$OUT/$N.build.log 2>&1 || { echo "$N BUILD-FAILED (see $OUT/$N.build.log)"; tail -5 $OUT/$N.build.log; exit 1; }
ELF=build/lr-bench-$N.elf
[ -f build/rv32_fast ] || cc -O2 -o build/rv32_fast tools/rv32_fast.c
R=$(TOKCOST=1 FBADDR=270 FBLOG=$OUT/$N.fb TICLIST=1 SYMELF=build/lr-bench-$N/doomd.elf build/rv32_fast $ELF $IMG 154 15c $OUT/$N.bin 4000000000 2>&1 | grep -aE "^(steps|GAMETICS|TOKENS)" | sed -E "s/ (per_instr|R|J|nt_or_x0|store|div|load|alu)=[^ ]*//g; s/^TOKENS total=([0-9]+) steps=[0-9]+.*/tokens=\1/" | tr '\n' ' ')
SZ=$(llvm-size -A build/lr-bench-$N/doomd.elf 2>/dev/null || size -A build/lr-bench-$N/doomd.elf)
sec() { echo "$SZ" | awk -v s=$1 '$1==s{print $2}'; }
MD=$(md5 -q $OUT/$N.bin 2>/dev/null || md5sum $OUT/$N.bin | cut -d' ' -f1)
FB=$(md5 -q $OUT/$N.fb 2>/dev/null || md5sum $OUT/$N.fb | cut -d" " -f1)
echo "$N $R text=$(sec .text) rodata=$(sec .rodata) data=$(sec .data) bss=$(sec .bss) md5=$MD fbmd5=$FB"
