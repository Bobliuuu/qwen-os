// SPDX-License-Identifier: GPL-2.0-or-later
// /bin/doomd: R_SolidColumn (plan D floors and ceilings in one colour per light row) is a
// function of (rows, plane height, colour, light) only. Neighbouring columns of a plane repeat
// the call with identical arguments, so a repeat is a copy of the column just drawn. Linked with
// --wrap=R_SolidColumn; the result is byte-identical (checked by frame dumps).
#include <stdint.h>
#include <string.h>

void __real_R_SolidColumn(uint8_t *dest, int y, int n, int32_t planeheight, int c, int startmap,
                          const uint8_t *cmaps, const uint8_t *fixedmap);

static struct { const uint8_t *dest; int32_t ph; const uint8_t *cmaps, *fixed; uint16_t y, n; int16_t c, sm; } last;

void __wrap_R_SolidColumn(uint8_t *dest, int y, int n, int32_t planeheight, int c, int startmap,
                          const uint8_t *cmaps, const uint8_t *fixedmap)
{
    if (last.dest && last.y == y && last.n == n && last.ph == planeheight && last.c == c &&
        last.sm == startmap && last.cmaps == cmaps && last.fixed == fixedmap) {
        memcpy(dest, last.dest, (uint32_t)n);
    } else {
        __real_R_SolidColumn(dest, y, n, planeheight, c, startmap, cmaps, fixedmap);
    }
    last.dest = dest; last.y = (uint16_t)y; last.n = (uint16_t)n; last.ph = planeheight;
    last.c = (int16_t)c; last.sm = (int16_t)startmap; last.cmaps = cmaps; last.fixed = fixedmap;
}
