// SPDX-License-Identifier: GPL-2.0-or-later
// /bin/doomd: switch for the map streams baked into the data ROM (bakemap.c, made by
// tools/bake_map.py). Only enabled when the image's map entry matches the baked offset, size and
// CRC; otherwise every read goes through the record cache and the disk as before.
#include <stdint.h>
#include "img.h"
#include "rec.h"

extern const uint32_t bake_key[5], bake_rng[][3];
uint32_t bake_lo, bake_span;
extern uint32_t bake_n;

void bake_init(void)
{
    if (!bake_n) return;
    int k = map_find((int)bake_key[0], (int)bake_key[1]);
    if (k < 0) return;
    dmc_mapent_t e;
    img_mapent(k, &e);
    if (e.off != bake_key[2] || e.size != bake_key[3] || e.crc != bake_key[4]) return;
    uint32_t lo = ~0u, hi = 0;
    for (uint32_t i = 0; i < bake_n; i++) {
        if (bake_rng[i][0] < lo) lo = bake_rng[i][0];
        if (bake_rng[i][0] + bake_rng[i][1] > hi) hi = bake_rng[i][0] + bake_rng[i][1];
    }
    bake_lo = lo; bake_span = hi - lo;
}
