#!/bin/bash
# Build the DMC100-Doom engine for QwenOS RV32IM as one ROM-linked app (/bin/doomd).
# usage: build.sh [outdir]   env: DMC (DMC100-Doom checkout), GEN (converter gen/ dir)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$HERE/../..
DMC=${DMC:-/Users/jhome/qwenos-work/engine/DMC100-Doom}
GEN=${GEN:-$DMC/build/sw/gen}
OUT=${1:-$HERE/../../build/doomd}
LLVM=${LLVM:-/opt/homebrew/opt/llvm/bin}
CC=${CC:-clang}; LD=${LD:-ld.lld}
mkdir -p "$OUT/o"
ARCH="--target=riscv32-unknown-elf -march=rv32im -mabi=ilp32 -msmall-data-limit=0 -mno-relax"
INC="-I$HERE/stub -I$DMC/engine/stub/include -I$DMC/engine -I$DMC/port/data -I$DMC/port/render -I$DMC/port/obj -I$DMC/port/math -I$DMC/platform -I$DMC/port/game -I$DMC/port/ovl -I$HERE -I$GEN -I$DMC/controller/rc-n1 -I$REPO/include -I$REPO/ports/doom"
DEFS="-DDOOMD_MODE=${DOOMD_MODE:-0} -DDOOMD_DUMP=${DOOMD_DUMP:-0} -DDMC_FW -DDMC_HASHORDER -DDMC_SINE_L1 -DPLAT_HOST"
CF="$ARCH ${OPT:--O2} -ffunction-sections -fdata-sections -ffreestanding -fno-builtin -fno-common -fwrapv -fsigned-char -std=gnu11 -w $DEFS $INC ${EXTRA_CF}"
# map streams in the data ROM (disk-request cut): BAKE_IMG = NOR image to read E1M6 from (default: the E1 pack)
BAKE_IMG=${BAKE_IMG:-$DMC/build/sw/nor/E1.img}
BAKE=$HERE/bakemap_stub.c
if [ -z "$NOBAKE" ] && [ -f "$BAKE_IMG" ]; then
  python3 $REPO/tools/bake_map.py "$BAKE_IMG" $OUT/bakemap.c ${BAKE_BUDGET:-82000} ${BAKE_EP:-1} ${BAKE_MAP:-6} >/dev/null && BAKE=$OUT/bakemap.c
fi
SRCS=""
for f in $DMC/engine/*.c; do
  b=$(basename $f .c); case $b in am_map|z_zone|m_argv|w_wad|w_file|i_endoom|m_fixed) continue;; esac; SRCS="$SRCS $f"
done
for f in $DMC/port/data/*.c $DMC/port/render/*.c $DMC/port/math/trig.c $DMC/port/obj/*.c; do
  b=$(basename $f .c); SRCS="$SRCS $f"
done
for b in i_dmc libc_dmc fe_glue i_input s_pcspk l_level l_lines l_menu l_wi l_finale g_save l_save; do SRCS="$SRCS $DMC/port/game/$b.c"; done
SRCS="$SRCS $GEN/info.c $GEN/colormap.c $GEN/trig_tables.c $GEN/view.c"
SRCS="$SRCS $DMC/platform/rt.c $DMC/platform/text.c $HERE/qplat.c $REPO/ports/doom/hal.c $HERE/doomd_main.c $HERE/ovl_rv.c $HERE/fastfix.c $HERE/rtlib.c $HERE/qimg.c $HERE/qsolid.c $HERE/qbake.c $BAKE $HERE/qnor.c $HERE/qlcd.c"
objs=""
$CC $ARCH -c $REPO/apps/doomd_crt0.S -o $OUT/o/crt0.o
objs="$OUT/o/crt0.o"
n=0
for s in $SRCS; do
  b=$(basename $s .c); o=$OUT/o/$b.o; case $s in $GEN/*) o=$OUT/o/gen_$b.o;; esac; objs="$objs $o"
  extra=""; [ $b = r_inner ] && extra="${INNER_CF:--O2 -fno-unroll-loops}"
  # the overlay entry tables must call the real (unwrapped) engine functions
  case $b in
   l_level) extra="-DG_DoLoadLevel=__real_G_DoLoadLevel -DG_DoNewGame=__real_G_DoNewGame -DG_DoPlayDemo=__real_G_DoPlayDemo -DG_DoWorldDone=__real_G_DoWorldDone -DP_Init=__real_P_Init";;
   l_lines) extra="-DP_CrossSpecialLine=__real_P_CrossSpecialLine -DP_ShootSpecialLine=__real_P_ShootSpecialLine -DP_UseSpecialLine=__real_P_UseSpecialLine";;
   i_dmc) extra="-Dpal_read=q_pal_set";;
   l_wi) extra="-DG_DoCompleted=__real_G_DoCompleted";;
  esac
  if [ ! -f $o ] || [ $s -nt $o ] || [ -n "$FORCE" ]; then
    $CC $CF $extra -c $s -o $o &
    n=$((n+1)); if [ $n -ge 8 ]; then wait; n=0; fi
  fi
done
wait
WRAP="--wrap=G_DoLoadLevel --wrap=G_DoNewGame --wrap=G_DoPlayDemo --wrap=G_DoCompleted --wrap=G_DoWorldDone --wrap=P_Init --wrap=R_SolidColumn --wrap=img_read --wrap=img_read_async --wrap=D_PostEvent --wrap=P_CrossSpecialLine --wrap=P_ShootSpecialLine --wrap=P_UseSpecialLine"
$LD --gc-sections --no-relax -T $REPO/linker/doomd.ld $HERE/frame.ld -z max-page-size=4 $WRAP --defsym=DOOMD_STACK_OVERRIDE=${STACK:-0x580} ${LDX} -Map $OUT/doomd.map -o $OUT/doomd.elf $objs
readelf -SW $OUT/doomd.elf | grep -E " \.(text|rodata|data|bss) "
