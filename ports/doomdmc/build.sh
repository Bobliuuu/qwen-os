#!/bin/bash
# Build the DMC100-Doom engine for QwenOS RV32IM as one ROM-linked app (/bin/doomd).
# usage: build.sh [outdir]   env: DMC (DMC100-Doom checkout), GEN (converter gen/ dir)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$HERE/../..
DMC=${DMC:-$REPO/.deps/engine/DMC100-Doom}
GEN=${GEN:-$DMC/build/sw/gen}
OUT=${1:-$HERE/../../build/doomd}
LLVM=${LLVM:-/opt/homebrew/opt/llvm/bin}
CC=${CC:-clang}; LD=${LD:-ld.lld}
mkdir -p "$OUT/o"
ARCH="--target=riscv32-unknown-elf -march=rv32im -mabi=ilp32 -msmall-data-limit=0 ${RELAXFLAG:--mrelax}"
INC="-I$HERE/stub -I$DMC/engine/stub/include -I$DMC/engine -I$DMC/port/data -I$DMC/port/render -I$DMC/port/obj -I$DMC/port/math -I$DMC/platform -I$DMC/port/game -I$DMC/port/ovl -I$HERE -I$GEN -I$DMC/controller/rc-n1 -I$REPO/include -I$REPO/ports/doom"
FLATDEF=-DQOS_FLATROM; [ "${FLATS:-off}" = off ] && FLATDEF=
DEFS="-DDOOMD_MODE=${DOOMD_MODE:-0} -DDOOMD_DUMP=${DOOMD_DUMP:-0} -DDMC_FW $FLATDEF -DDMC_HASHORDER -DDMC_SINE_L1 -DPLAT_HOST"
[ -n "$QHASH" ] && INC="$INC -I$DMC/tests/lockstep" && EXTRA_CF="$EXTRA_CF -DQ_STATE_HASH"
[ -n "$QTRACE" ] && EXTRA_CF="$EXTRA_CF -DQ_TRACE_TIC=$QTRACE"
CF="$ARCH ${OPT:--O2} -ffunction-sections -fdata-sections -ffreestanding -fno-builtin -fno-common -fwrapv -fsigned-char -std=gnu11 -w $DEFS $INC ${EXTRA_CF}"
# map streams in the data ROM (disk-request cut): BAKE_IMG = NOR image to read E1M6 from (default: the E1 pack)
BAKE_IMG=${BAKE_IMG:-$DMC/build/sw/nor/E1.img}
BAKE=$HERE/bakemap_stub.c
if [ -z "$NOBAKE" ] && [ -f "$BAKE_IMG" ]; then
  python3 $REPO/tools/bake_map.py "$BAKE_IMG" $OUT/bakemap.c ${BAKE_BUDGET:-82000} ${BAKE_EP:-1} ${BAKE_MAP:-1} >/dev/null && BAKE=$OUT/bakemap.c
fi
# flats in the data ROM (fetch.c hook, mkflatrom.py): FLATS=all (88 flats of E1, 90 KB) | map (only QFLAT_MAPS, default E1M1) | none
# data ROM is shared with the map bake above: BAKE_BUDGET + flats must fit (the linker errors out otherwise)
PACK=${PACK:-$DMC/build/sw/packs/E1}
case ${FLATS:-off} in
  off) :;;
  all) QFLATS_MAX=${QFLATS_MAX:-88} python3 -I $HERE/mkflatrom.py $DMC $PACK $OUT/flatrom.c >/dev/null;;
  map) QFLAT_MAPS=${QFLAT_MAPS:-E1M1} QFLATS_MAX=${QFLATS_MAX:-88} python3 -I $HERE/mkflatrom.py $DMC $PACK $OUT/flatrom.c >/dev/null;;
  *)   QFLATS_MAX=0 python3 -I $HERE/mkflatrom.py $DMC $PACK $OUT/flatrom.c >/dev/null;;
esac
SRCS=""
for f in $DMC/engine/*.c; do
  b=$(basename $f .c); case $b in am_map|z_zone|m_argv|w_wad|w_file|i_endoom) continue;; m_fixed) [ -n "$NOFASTFIX" ] || continue;; esac; SRCS="$SRCS $f"
done
for f in $DMC/port/data/*.c $DMC/port/render/*.c $DMC/port/math/trig.c $DMC/port/obj/*.c; do
  b=$(basename $f .c); case $b in crc32) continue;; esac; SRCS="$SRCS $f"   # crc32 -> ports/doomdmc/qcrc.c
done
for b in i_dmc libc_dmc fe_glue i_input s_pcspk l_level l_lines l_menu l_wi l_finale g_save l_save; do SRCS="$SRCS $DMC/port/game/$b.c"; done
SRCS="$SRCS $GEN/info.c $GEN/colormap.c $GEN/trig_tables.c $GEN/view.c"
# QHASH=1: verification build with the lockstep game-state hash after every tic (qhash.c)
if [ -n "$QHASH" ]; then
  HASHC=$DMC/tests/lockstep/hash.c
  if [ -n "$QTRACE" ]; then   # QTRACE=tic: every hashed value of that tic is printed ("T name idx value")
    python3 - "$HASHC" "$OUT/hash_trace.c" <<'PY'
import sys
s=open(sys.argv[1]).read().replace("    (void)name;\n    (void)idx;","    q_trace_put(name, idx, v);",1)
open(sys.argv[2],'w').write('void q_trace_put(const char*,int,int);\n'+s)
PY
    HASHC=$OUT/hash_trace.c
  fi
  SRCS="$SRCS $HASHC $HERE/qhash.c"; LDX="$LDX --wrap=G_Ticker"
fi
SRCS="$SRCS $DMC/platform/rt.c $DMC/platform/text.c $HERE/qplat.c $REPO/ports/doom/hal.c $HERE/doomd_main.c $HERE/ovl_rv.c $([ -n "$NOFASTFIX" ] || echo $HERE/fastfix.c) $HERE/rtlib.c $([ -n "$NOQIMG" ] || echo $HERE/qimg.c) $([ -n "$NOSOLID" ] || echo $HERE/qsolid.c) $HERE/qbake.c $BAKE $([ "${FLATS:-off}" = off ] || echo $OUT/flatrom.c) $HERE/qnor.c $HERE/qlcd.c $HERE/qcrc.c"
objs=""
$CC $ARCH -c $REPO/apps/doomd_crt0.S -o $OUT/o/crt0.o
objs="$OUT/o/crt0.o"
n=0
for s in $SRCS; do
  b=$(basename $s .c); o=$OUT/o/$b.o; case $s in $OUT/flatrom.c) o=$OUT/o/flatrom.o;; $GEN/*) o=$OUT/o/gen_$b.o;; esac; objs="$objs $o"
  extra=""; [ $b = r_inner ] && extra="${INNER_CF:--O2 -fno-unroll-loops}"
  # the overlay entry tables must call the real (unwrapped) engine functions
  case $b in
   l_level) extra="-DG_DoLoadLevel=__real_G_DoLoadLevel -DG_DoNewGame=__real_G_DoNewGame -DG_DoPlayDemo=__real_G_DoPlayDemo -DG_DoWorldDone=__real_G_DoWorldDone -DP_Init=__real_P_Init";;
   l_lines) extra="-DP_CrossSpecialLine=__real_P_CrossSpecialLine -DP_ShootSpecialLine=__real_P_ShootSpecialLine -DP_UseSpecialLine=__real_P_UseSpecialLine";;
   i_dmc) extra="-Dpal_read=q_pal_set";;
   hash|hash_trace) extra="-DLS_SMALL -DLS_NOFILE -Drndindex=ls_zero_rnd";;
   l_wi) extra="-DG_DoCompleted=__real_G_DoCompleted";;
  esac
  if [ ! -f $o ] || [ $s -nt $o ] || [ -n "$FORCE" ]; then
    $CC $CF $extra -c $s -o $o &
    n=$((n+1)); if [ $n -ge 8 ]; then wait; n=0; fi
  fi
done
wait
WRAP="--wrap=G_DoLoadLevel --wrap=G_DoNewGame --wrap=G_DoPlayDemo --wrap=G_DoCompleted --wrap=G_DoWorldDone --wrap=P_Init $([ -n "$NOSOLID" ] || echo --wrap=R_SolidColumn) $([ -n "$NOQIMG" ] || echo "--wrap=img_read --wrap=img_read_async") --wrap=D_PostEvent --wrap=P_CrossSpecialLine --wrap=P_ShootSpecialLine --wrap=P_UseSpecialLine"
$LD --gc-sections ${LDRELAX:---relax --relax-gp} -T $REPO/linker/doomd.ld $HERE/frame.ld -z max-page-size=4 $WRAP --defsym=DOOMD_STACK_OVERRIDE=${STACK:-0x580} ${LDX} -Map $OUT/doomd.map -o $OUT/doomd.elf $objs
readelf -SW $OUT/doomd.elf | grep -E " \.(text|rodata|data|bss) "
