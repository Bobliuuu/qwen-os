// SPDX-License-Identifier: GPL-2.0-or-later
// /bin/doomd: R_SolidColumn (plan D floors and ceilings in one colour per light row) is a
// function of (rows, plane height, colour, light) only (its tables are const). Neighbouring
// columns of a plane repeat the call with identical arguments, so a repeat is a copy of the
// column just computed. Linked with --wrap=R_SolidColumn; the result is byte-identical
// (checked by tools/doomd_regress.sh frame hashes).
//
// The copy comes from a PRIVATE buffer, never from the previous destination column: the strip
// buffer column that was just drawn can be overdrawn (wall/sprite pixels, e.g. row 199 of the
// DEMO1 frame at unique index 202) before the next plane column is requested, and copying that
// column would replicate the overdraw across the whole run of columns.
#include <stdint.h>
#include <string.h>

void __real_R_SolidColumn(uint8_t *dest, int y, int n, int32_t planeheight, int c, int startmap,
                          const uint8_t *cmaps, const uint8_t *fixedmap);

/* RAM is the limit here (the level arena takes whatever .bss leaves; 200 B for a column copy
 * already makes "plan D: caches end 48 B into the arena" panic), so the last column is kept as
 * runs of equal bytes (one run per light row, at most Q_SOLID_RUNS of them): 2 B per run. */
#define Q_SOLID_MAX  200 /* R_VIEWH */
#define Q_SOLID_RUNS 24
static struct { const uint8_t *cmaps, *fixed; int32_t ph; uint8_t y, n, c, sm, valid, nr; } last; /* y < 200, n <= 200, c a colour, sm 0..31 */
static uint8_t run_at[Q_SOLID_RUNS], run_val[Q_SOLID_RUNS]; /* row offset of the run, its byte */

void __wrap_R_SolidColumn(uint8_t *dest, int y, int n, int32_t planeheight, int c, int startmap,
                          const uint8_t *cmaps, const uint8_t *fixedmap)
{
    if (n <= 0 || n > Q_SOLID_MAX) {           /* not cacheable: behave exactly like the original */
        last.valid = 0;
        __real_R_SolidColumn(dest, y, n, planeheight, c, startmap, cmaps, fixedmap);
        return;
    }
    if (last.valid && last.y == y && last.n == n && last.ph == planeheight && last.c == c &&
        last.sm == startmap && last.cmaps == cmaps && last.fixed == fixedmap) {
        for (unsigned i = 0; i < last.nr; i++) {
            unsigned end = i + 1 < last.nr ? run_at[i + 1] : (unsigned)n;
            memset(dest + run_at[i], run_val[i], end - run_at[i]);
        }
        return;
    }
    __real_R_SolidColumn(dest, y, n, planeheight, c, startmap, cmaps, fixedmap);
    unsigned nr = 0;
    last.valid = 0;
    for (int i = 0; i < n; i++) {
        if (i && dest[i] == dest[i - 1]) continue;
        if (nr == Q_SOLID_RUNS) return;        /* too many runs: leave the cache invalid */
        run_at[nr] = (uint8_t)i; run_val[nr] = dest[i]; nr++;
    }
    last.nr = (uint8_t)nr; last.valid = 1; last.y = (uint8_t)y; last.n = (uint8_t)n;
    last.ph = planeheight; last.c = (uint8_t)c; last.sm = (uint8_t)startmap;
    last.cmaps = cmaps; last.fixed = fixedmap;
}
