#!/bin/bash
# Build the DMC100 host oracle (unmodified doomgeneric + hash hooks) on macOS, where ld has no
# --wrap: the defining files are compiled with the wrapped names renamed to __real_*, and the
# hook files with __wrap_* renamed to the plain names (same effect as ld --wrap: only calls
# from other translation units are redirected).
# usage: build_oracle_mac.sh DMC_DIR   -> DMC_DIR/build/oracle/dg_oracle
set -e
DMC=${1:-/Users/jhome/qwenos-work/engine/DMC100-Doom}
cd "$DMC"
CC=${CC:-clang}
make oracle ENG_CC=$CC >/dev/null 2>&1 || true   # compiles all objects; link fails on macOS (ignored)
O=build/oracle
SRC=oracle/src/doomgeneric-repo/doomgeneric
CF="-O2 -g -std=gnu11 -w -fwrapv -fsigned-char -DNORMALUNIX -DLINUX -D_DEFAULT_SOURCE -DCMAP256 -DDOOMGENERIC_RESX=320 -DDOOMGENERIC_RESY=200 -I$SRC -Ioracle -Itests/lockstep"
ren() { local o=""; for f in "$@"; do o="$o -D$f=__real_$f"; done; echo $o; }
unw() { local o=""; for f in "$@"; do o="$o -D__wrap_$f=$f"; done; echo $o; }
$CC $CF $(ren G_Ticker G_BuildTiccmd G_DeferedPlayDemo G_TimeDemo G_ExitLevel G_SecretExitLevel) -c $SRC/g_game.c -o $O/up/g_game.o
$CC $CF $(ren I_Quit I_Error) -c $SRC/i_system.c -o $O/up/i_system.o
$CC $CF $(ren I_SetPalette) -c $SRC/i_video.c -o $O/up/i_video.o
$CC $CF $(ren P_PlayerThink) -c $SRC/p_user.c -o $O/up/p_user.o
$CC $CF $(ren M_Drawer) -c $SRC/m_menu.c -o $O/up/m_menu.o
$CC $CF $(ren F_StartFinale) -c $SRC/f_finale.c -o $O/up/f_finale.o
W="G_Ticker G_BuildTiccmd I_Quit I_Error G_DeferedPlayDemo G_TimeDemo I_SetPalette P_PlayerThink G_ExitLevel G_SecretExitLevel M_Drawer F_StartFinale"
$CC $CF $(unw $W) -c oracle/hash_hook.c -o $O/own/hash_hook.o
$CC $CF $(unw $W) -c tests/lockstep/play.c -o $O/own/play.o
# hash without rndindex (M_Random counts frame draws, cosmetic), same as the guest's qhash build
$CC $CF -Drndindex=ls_zero_rnd -c tests/lockstep/hash.c -o $O/own/hash.o
echo "int ls_zero_rnd;" > $O/zr.c; $CC -c $O/zr.c -o $O/own/zr.o
# hook files call the wrapped names they mean to reach through __real_*; rename calls inside them
$CC -o $O/dg_oracle $O/up/*.o $O/own/*.o -lm
echo built $O/dg_oracle
