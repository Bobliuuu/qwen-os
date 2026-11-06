// SPDX-License-Identifier: GPL-2.0-or-later
// Verification build only (EXTRA_SRC=qhash.c, LDX=--wrap=G_Ticker, see tools/doomd_regress.sh):
// the lockstep game-state hash of tests/lockstep/hash.c (identical to the host oracle's
// stream, FNV-1a over players, sectors and every live mobj) after every game tic, printed as
//   "TICHASH <gametic> <16 hex>\n"
// The scratch the hash needs (2 B per handle slot) is borrowed from the frame area, which
// is dead between G_Ticker and D_Display except for the strip cache, so frame hashes of a
// hash build are only comparable with each other, not with the plain build.
#include <stdint.h>
#include "doomdef.h"
#include "doomstat.h"
#include "hash.h"
#include "qplat.h"
#include "things.h"

/* hash.c is built with -Drndindex=ls_zero_rnd: rndindex (M_Random) is cosmetic and counts frame
 * draws (wipes), which differ between a draw-per-tic oracle and this loop, so it is not hashed */
const int ls_zero_rnd = 0; /* rodata: RAM is full, a bss word can push "plan D" over the edge */
extern uint8_t __frame_start[], __ram_end[];
void __real_G_Ticker(void);

void __wrap_G_Ticker(void)
{
    int t = gametic;
    __real_G_Ticker();
    if (gamestate != GS_LEVEL) return;
    uint32_t bytes = (uint32_t)(__ram_end - __frame_start);
    uint64_t h = LS_HashScratch(__frame_start, bytes > 6144 ? 6144 : bytes);
    for (int i = 0; i < EV_COUNT; i++)   /* object-store events (page pool exhausted...) change the game */
        if (o_stats.events[i]) { q_puts("TICEVENTS "); q_putu((uint32_t)t); q_putc(' '); q_putu((uint32_t)i); q_putc('\n'); break; }
    q_puts("TICHASH "); q_putu((uint32_t)t); q_putc(' ');
    q_puthex((uint32_t)(h >> 32)); q_puthex((uint32_t)h); q_putc('\n');
}

#ifdef Q_TRACE_TIC
void q_trace_put(const char *name, int idx, int v)
{
    if (gametic != Q_TRACE_TIC) return;
    q_puts("T "); q_puts(name); q_putc(' '); q_putu((uint32_t)idx); q_putc(' '); q_putu((uint32_t)v); q_putc('\n');
}
#endif
