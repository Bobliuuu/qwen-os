// SPDX-License-Identifier: GPL-2.0-or-later
// Copyright (C) 2026 Artur Bieniek

#include <string.h>

#include "cache.h"
#include "img.h"
#include "nor.h"

#ifdef DMC_FW
// Map streams baked into the data ROM (ports/doomdmc/qbake.c, bakemap.c): reads inside them never
// touch the cache or the disk. bake_span is 0 unless the image's map entry matches the baked one.
extern uint32_t bake_lo, bake_span, bake_n;
extern const uint32_t bake_rng[][3], bake_data[];
static inline const uint8_t *bake_ptr(uint32_t loff, uint32_t n)
{
    if (loff - bake_lo >= bake_span)
        return 0;
    for (uint32_t i = 0; i < bake_n; i++) {
        uint32_t rel = loff - bake_rng[i][0];
        if (rel < bake_rng[i][1] && n <= bake_rng[i][1] - rel)
            return (const uint8_t *)bake_data + bake_rng[i][2] + rel;
    }
    return 0;
}
#else
#define bake_span 0u
#define bake_lo 0u
#define bake_ptr(l, n) ((const uint8_t *)0)
#endif

#define RC_NOTAG 0xFFFFu
// MRU way in bits 0-1 up to the LRU way in bits 6-7
#define RC_LRU_INIT 0xE4u

#ifdef DMC_FW
static uint8_t *rc_mem;
#else
static uint8_t rc_mem[RC_BYTES] __attribute__((aligned(4)));
#endif
#define rc_data ((uint8_t (*)[RC_LINE])rc_mem)
#define rc_tag ((uint16_t *)(rc_mem + RC_LINES * RC_LINE))
#define rc_lru (rc_mem + RC_LINES * RC_LINE + RC_LINES * 2)

#ifndef DMC_FW
uint32_t rc_hits, rc_misses;
#endif

void rc_reset(void)
{
    for (int i = 0; i < RC_LINES; i++)
        rc_tag[i] = RC_NOTAG;
    for (int s = 0; s < RC_SETS; s++)
        rc_lru[s] = RC_LRU_INIT;
}

#ifdef DMC_FW
void rc_place(void *base)
{
    rc_mem = base;
    rc_reset();
}
#endif

#ifdef DMC_HOST
static uint8_t *rc2_mem;
#define rc2_data ((uint8_t (*)[RC_LINE])rc2_mem)
#define rc2_tag ((uint16_t *)(rc2_mem + RC2_LINES * RC_LINE))

void rc2_begin(void *base)
{
    rc2_mem = base;
    for (int i = 0; base && i < RC2_LINES; i++)
        rc2_tag[i] = RC_NOTAG;
}

void rc2_end(void)
{
#ifdef DMC_STATS
    // nothing may rely on what it held
    if (rc2_mem)
        memset(rc2_mem, 0xA5, RC2_BYTES);
#endif
    rc2_mem = NULL;
}

void rc2_drop(void)
{
    rc2_mem = NULL;
}

// Miss of line ln whose set evicts way w: the evicted line
// moves to the second level. Returns 1 when ln came from
// there into the way.
static int rc2_swap(uint32_t ln, unsigned set, unsigned w, uint16_t old)
{
    unsigned s = ln & (RC2_LINES - 1);
    uint8_t want[RC_LINE];
    int hit = rc2_tag[s] == (uint16_t)(ln / RC2_LINES);
    // the wanted line is taken out first, the evicted one
    // may go to the same set
    if (hit)
        memcpy(want, rc2_data[s], RC_LINE);
    if (old != RC_NOTAG) {
        uint32_t vln = (uint32_t)old * RC_SETS + set;
        unsigned v = vln & (RC2_LINES - 1);
        memcpy(rc2_data[v], rc_data[set * RC_WAYS + w], RC_LINE);
        rc2_tag[v] = (uint16_t)(vln / RC2_LINES);
#ifdef DMC_STATS
        rc2_stat_hook(vln * RC_LINE, 0);
#endif
    }
    if (hit) {
        memcpy(rc_data[set * RC_WAYS + w], want, RC_LINE);
#ifdef DMC_STATS
        rc2_stat_hook(ln * RC_LINE, 1);
#endif
    }
    return hit;
}
#endif

// Moves way w to the MRU position (table lookup, generated from the shift loop of the original).
static const uint8_t lru_tab[4][256] = {
    {0,4,8,12,4,20,24,28,8,36,40,44,12,52,56,60,16,20,24,28,20,84,88,92,24,100,104,108,28,116,120,124,32,36,40,44,36,148,152,156,40,164,168,172,44,180,184,188,48,52,56,60,52,212,216,220,56,228,232,236,60,244,248,252,64,68,72,76,68,84,88,92,72,100,104,108,76,116,120,124,80,84,88,92,84,0,0,0,88,0,0,0,92,0,0,0,96,100,104,108,100,0,0,0,104,0,0,0,108,0,0,0,112,116,120,124,116,0,0,0,120,0,0,0,124,0,0,0,128,132,136,140,132,148,152,156,136,164,168,172,140,180,184,188,144,148,152,156,148,0,0,0,152,0,0,0,156,0,0,0,160,164,168,172,164,0,0,0,168,0,0,0,172,0,0,0,176,180,184,188,180,0,0,0,184,0,0,0,188,0,0,0,192,196,200,204,196,212,216,220,200,228,232,236,204,244,248,252,208,212,216,220,212,0,0,0,216,0,0,0,220,0,0,0,224,228,232,236,228,0,0,0,232,0,0,0,236,0,0,0,240,244,248,252,244,0,0,0,248,0,0,0,252,0,0,0},
    {0,1,0,0,1,5,9,13,0,9,0,0,0,13,0,0,1,17,9,13,17,21,25,29,33,25,41,45,49,29,57,61,0,33,0,0,33,37,41,45,0,41,0,0,0,45,0,0,0,49,0,0,49,53,57,61,0,57,0,0,0,61,0,0,1,65,9,13,65,69,73,77,33,73,41,45,49,77,57,61,65,81,73,77,81,85,89,93,97,89,105,109,113,93,121,125,129,97,137,141,97,101,105,109,161,105,169,173,177,109,185,189,193,113,201,205,113,117,121,125,225,121,233,237,241,125,249,253,0,129,0,0,129,133,137,141,0,137,0,0,0,141,0,0,129,145,137,141,145,149,153,157,161,153,169,173,177,157,185,189,0,161,0,0,161,165,169,173,0,169,0,0,0,173,0,0,0,177,0,0,177,181,185,189,0,185,0,0,0,189,0,0,0,193,0,0,193,197,201,205,0,201,0,0,0,205,0,0,193,209,201,205,209,213,217,221,225,217,233,237,241,221,249,253,0,225,0,0,225,229,233,237,0,233,0,0,0,237,0,0,0,241,0,0,241,245,249,253,0,249,0,0,0,253,0,0},
    {0,0,2,0,0,0,6,0,2,6,10,14,0,0,14,0,0,0,18,0,0,0,22,0,18,22,26,30,0,0,30,0,2,6,34,14,18,22,38,30,34,38,42,46,50,54,46,62,0,0,50,0,0,0,54,0,50,54,58,62,0,0,62,0,0,0,66,0,0,0,70,0,66,70,74,78,0,0,78,0,0,0,82,0,0,0,86,0,82,86,90,94,0,0,94,0,66,70,98,78,82,86,102,94,98,102,106,110,114,118,110,126,0,0,114,0,0,0,118,0,114,118,122,126,0,0,126,0,2,6,130,14,18,22,134,30,130,134,138,142,50,54,142,62,66,70,146,78,82,86,150,94,146,150,154,158,114,118,158,126,130,134,162,142,146,150,166,158,162,166,170,174,178,182,174,190,194,198,178,206,210,214,182,222,178,182,186,190,242,246,190,254,0,0,194,0,0,0,198,0,194,198,202,206,0,0,206,0,0,0,210,0,0,0,214,0,210,214,218,222,0,0,222,0,194,198,226,206,210,214,230,222,226,230,234,238,242,246,238,254,0,0,242,0,0,0,246,0,242,246,250,254,0,0,254,0},
    {0,0,0,3,0,0,0,7,0,0,0,11,3,7,11,15,0,0,0,19,0,0,0,23,0,0,0,27,19,23,27,31,0,0,0,35,0,0,0,39,0,0,0,43,35,39,43,47,3,7,11,51,19,23,27,55,35,39,43,59,51,55,59,63,0,0,0,67,0,0,0,71,0,0,0,75,67,71,75,79,0,0,0,83,0,0,0,87,0,0,0,91,83,87,91,95,0,0,0,99,0,0,0,103,0,0,0,107,99,103,107,111,67,71,75,115,83,87,91,119,99,103,107,123,115,119,123,127,0,0,0,131,0,0,0,135,0,0,0,139,131,135,139,143,0,0,0,147,0,0,0,151,0,0,0,155,147,151,155,159,0,0,0,163,0,0,0,167,0,0,0,171,163,167,171,175,131,135,139,179,147,151,155,183,163,167,171,187,179,183,187,191,3,7,11,195,19,23,27,199,35,39,43,203,195,199,203,207,67,71,75,211,83,87,91,215,99,103,107,219,211,215,219,223,131,135,139,227,147,151,155,231,163,167,171,235,227,231,235,239,195,199,203,243,211,215,219,247,227,231,235,251,243,247,251,255}
};

static inline uint8_t lru_touch(uint8_t l, unsigned w)
{
    return lru_tab[w][l];
}

// Miss of logical line number ln: the LRU way of its set gets the line. Out
// of line, so the hit path of its callers saves fewer registers.
__attribute__((noinline)) static const uint8_t *rc_fill(uint32_t ln)
{
    unsigned set = ln & (RC_SETS - 1);
    uint16_t tag = (uint16_t)(ln / RC_SETS);
    unsigned base = set * RC_WAYS;
#ifndef DMC_FW
    rc_misses++;
#endif
#ifdef DMC_STATS
    rc_stat_hook(ln * RC_LINE, 0);
#endif
    unsigned w = rc_lru[set] >> 6;
#ifdef DMC_HOST
    uint16_t old = rc_tag[base + w];
#endif
    rc_tag[base + w] = RC_NOTAG;
    uint32_t loff = ln * RC_LINE;
    uint32_t n = RC_LINE;
    if (loff + n > img.size)
        n = img.size - loff;
#ifdef DMC_HOST
    if (!rc2_mem || !rc2_swap(ln, set, w, old))
#endif
    {
        const uint32_t *pw = img_pw[loff >= img.split];
        if (loff - pw[0] < pw[1] - pw[0] && pw[1] - loff >= n)
            nor_read(pw[2] + loff, rc_data[base + w], n);
        else
            img_read(loff, rc_data[base + w], n);
    }
    rc_tag[base + w] = tag;
    rc_lru[set] = lru_touch(rc_lru[set], w);
    return rc_data[base + w];
}

// Byte loff in the cache, its line looked up inline in rec_get.
// The four tags are compared without a loop, and a hit on the MRU way leaves
// the LRU byte as it is (lru_touch returns it unchanged for that way).
static inline __attribute__((always_inline)) const uint8_t *rc_at(uint32_t loff)
{
    uint32_t ln = loff / RC_LINE;
    unsigned set = ln & (RC_SETS - 1);
    uint16_t tag = (uint16_t)(ln / RC_SETS);
    const uint16_t *t = &rc_tag[set * RC_WAYS];
    unsigned w;

    if (t[0] == tag)
        w = 0;
    else if (t[1] == tag)
        w = 1;
    else if (t[2] == tag)
        w = 2;
    else if (t[3] == tag)
        w = 3;
    else
        return rc_fill(ln) + (loff & (RC_LINE - 1));
#ifndef DMC_FW
    rc_hits++;
#endif
#ifdef DMC_STATS
    rc_stat_hook(ln * RC_LINE, 1);
#endif
    const uint8_t *p = rc_data[set * RC_WAYS + w] + (loff & (RC_LINE - 1));
    uint8_t *lru = &rc_lru[set];
    if ((*lru & 3u) != w)
        *lru = lru_touch(*lru, w);
    return p;
}

// The copies of constant size below use __builtin_memcpy: the firmware is
// built freestanding, where memcpy is an ordinary call. Up to 8 B it becomes
// single loads and stores. Lines and destinations need not be word aligned,
// and the M4 does those unaligned (never LDRD, STRD, LDM or STM, which fault).
__attribute__((noinline)) static void rec_get_slow(uint32_t loff, void *out, uint32_t n)
{
    {
        const uint8_t *b = bake_ptr(loff, n);
        if (b) {
            memcpy(out, b, n);
            return;
        }
    }
    uint8_t *o = out;
    unsigned in = loff & (RC_LINE - 1);

    if (n - 1u < RC_LINE - in) {
        // in one line: every record and stream field
        const uint8_t *p = rc_at(loff);
        switch (n) {
        case 16:
            __builtin_memcpy(o, p, 8);
            __builtin_memcpy(o + 8, p + 8, 8);
            return;
        case 8:
            __builtin_memcpy(o, p, 8);
            return;
        case 4:
            __builtin_memcpy(o, p, 4);
            return;
        case 2:
            __builtin_memcpy(o, p, 2);
            return;
        case 1:
            *o = *p;
            return;
        }
        memcpy(o, p, n);
        return;
    }
    // across lines: the part in each line
    while (n) {
        unsigned k = RC_LINE - in;
        if (k > n)
            k = n;
        rec_get_slow(loff, o, k);
        o += k;
        loff += k;
        n -= k;
        in = 0;
    }
}

// Hit lookup without a fill: NULL on a miss (the hit path of rec_get stays a leaf function).
static inline __attribute__((always_inline)) const uint8_t *rc_hit(uint32_t loff)
{
    uint32_t ln = loff / RC_LINE;
    unsigned set = ln & (RC_SETS - 1);
    uint16_t tag = (uint16_t)(ln / RC_SETS);
    const uint16_t *t = &rc_tag[set * RC_WAYS];
    unsigned w;

    if (t[0] == tag)
        w = 0;
    else if (t[1] == tag)
        w = 1;
    else if (t[2] == tag)
        w = 2;
    else if (t[3] == tag)
        w = 3;
    else
        return 0;
    uint8_t *lru = &rc_lru[set];
    uint8_t l = *lru;
    if ((l & 3u) != w)
        *lru = lru_tab[w][l];
    return rc_data[set * RC_WAYS + w] + (loff & (RC_LINE - 1));
}

void rec_get(uint32_t loff, void *out, uint32_t n)
{
    const uint8_t *p = 0;
    if (loff - bake_lo < bake_span)
        p = bake_ptr(loff, n);
    if (!p && n - 1u < RC_LINE - (loff & (RC_LINE - 1)))
        p = rc_hit(loff);
    if (!p) {
        rec_get_slow(loff, out, n);
        return;
    }
    if (!(((uintptr_t)p | (uintptr_t)out) & 3u)) {
        const uint32_t *s = (const uint32_t *)(const void *)p;
        uint32_t *d = (uint32_t *)out;
        switch (n) {
        case 16: {
            uint32_t a = s[0], b = s[1], c = s[2], e = s[3];
            d[0] = a; d[1] = b; d[2] = c; d[3] = e;
            return;
        }
        case 8: {
            uint32_t a = s[0], b = s[1];
            d[0] = a; d[1] = b;
            return;
        }
        case 4:
            d[0] = s[0];
            return;
        case 12: {
            uint32_t a = s[0], b = s[1], c = s[2];
            d[0] = a; d[1] = b; d[2] = c;
            return;
        }
        }
    }
    memcpy(out, p, n);
}

uint16_t rec_u16(uint32_t loff)
{
    if (!(loff & 1u) && ((loff & (RC_LINE - 1)) <= RC_LINE - 2 || loff - bake_lo < bake_span)) {
        const uint8_t *p = loff - bake_lo < bake_span ? bake_ptr(loff, 2) : 0;
        if (!p && (loff & (RC_LINE - 1)) <= RC_LINE - 2)
            p = rc_hit(loff);
        if (p)
            return *(const uint16_t *)(const void *)p;
    }
    uint16_t v;
    rec_get_slow(loff, &v, 2);
    return v;
}

uint32_t rec_u32(uint32_t loff)
{
    if (!(loff & 3u)) {
        const uint8_t *p = loff - bake_lo < bake_span ? bake_ptr(loff, 4) : 0;
        if (!p)
            p = rc_hit(loff);
        if (p)
            return *(const uint32_t *)(const void *)p;
    }
    uint32_t v;
    rec_get_slow(loff, &v, 4);
    return v;
}
