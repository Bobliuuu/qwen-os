// SPDX-License-Identifier: GPL-2.0-or-later
// /bin/doomd: fast path in front of DMC100's img_read / img_read_async (linked with --wrap).
// The engine translates every 16-byte cache-line fill through a binary search of the FAT
// extents (ext_phys); here the last extent run is remembered, so a read inside it is one
// compare and an add. ~3,000 line fills per tic made that translation a measurable share.
#include <stdint.h>
#include "img.h"
#include "nor.h"

void nor_hw(uint32_t phys, void *dst, uint32_t n); /* qplat.c: no statistics */
void dmc_fatal(const char *msg);
uint32_t img_phys_run(uint32_t loff, uint32_t *run);

/* 4 remembered runs, picked by 4 KB block of the logical offset: logical [lo,hi) is physical
 * logical + delta. Reads alternate between map, texture and patch data, so one run thrashes. */
#define NRUN 4
static struct { uint32_t lo, hi, delta; } runs[NRUN];

static inline uint32_t phys_of(uint32_t loff, uint32_t *run)
{
    unsigned k = (loff >> 12) & (NRUN - 1);
    if (loff - runs[k].lo < runs[k].hi - runs[k].lo) {
        *run = runs[k].hi - loff;
        return loff + runs[k].delta;
    }
    uint32_t r;
    uint32_t p = img_phys_run(loff, &r);
    runs[k].lo = loff; runs[k].hi = loff + r; runs[k].delta = p - loff;
    *run = r;
    return p;
}

void __wrap_img_read(uint32_t loff, void *dst, uint32_t n)
{
    uint8_t *d = dst;
    if (loff > img.size || n > img.size - loff)
        dmc_fatal("image read out of range");
    while (n) {
        uint32_t run;
        uint32_t phys = phys_of(loff, &run);
        if (run > n) run = n;
        nor_hw(phys, d, run);
        d += run; loff += run; n -= run;
    }
}

int __wrap_img_read_async(uint32_t loff, void *dst, uint32_t n, int prio)
{
    uint8_t *d = dst;
    int t = 0;
    if (loff > img.size || n > img.size - loff)
        dmc_fatal("image read out of range");
    while (n) {
        uint32_t run;
        uint32_t phys = phys_of(loff, &run);
        if (run > n) run = n;
        nor_hw(phys, d, run);
        t = 1;
        d += run; loff += run; n -= run;
    }
    return t;
}
