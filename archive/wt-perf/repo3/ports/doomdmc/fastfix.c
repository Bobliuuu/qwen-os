// SPDX-License-Identifier: GPL-2.0-or-later
// Fixed-point multiply/divide for /bin/doomd, replacing engine/m_fixed.c in this build only.
// Same results bit for bit (checked against the bit-serial reference in tools/ or by
// ports/doomdmc/fixtest.c), but FixedDiv uses the RV32M divu instruction (about 40 instructions
// instead of 30 loop steps of 9) because every instruction costs chip tokens here.
#include <stdint.h>
#include <limits.h>
#include "doomtype.h"
#include "m_fixed.h"

fixed_t FixedMul(fixed_t a, fixed_t b)
{
    return (fixed_t)(((int64_t)a * (int64_t)b) >> FRACBITS);
}

// the original bit-serial quotient of (ua << 16) / ub mod 2^32, only for the a == INT_MIN corner
static uint32_t udiv_slow(uint32_t ua, uint32_t ub)
{
    uint32_t r = 0, n = ua, q = 0;
    int i = 48;
    while (i--) {
        r = (r << 1) | (n >> 31);
        n <<= 1;
        q <<= 1;
        if (r >= ub) { r -= ub; q |= 1; }
    }
    return q;
}

// (hi:lo) / d with hi < d (Hacker's Delight divlu), 16-bit digits, hardware 32-bit divide
static uint32_t divlu(uint32_t hi, uint32_t lo, uint32_t d)
{
    uint32_t s = 0;
    if (!(d >> 16)) { s += 16; d <<= 16; }
    if (!(d >> 24)) { s += 8;  d <<= 8; }
    if (!(d >> 28)) { s += 4;  d <<= 4; }
    if (!(d >> 30)) { s += 2;  d <<= 2; }
    if (!(d >> 31)) { s += 1;  d <<= 1; }
    uint32_t un32 = s ? (hi << s) | (lo >> (32 - s)) : hi;
    uint32_t un10 = lo << s;
    uint32_t vn1 = d >> 16, vn0 = d & 0xFFFF;
    uint32_t un1 = un10 >> 16, un0 = un10 & 0xFFFF;
    uint32_t q1 = un32 / vn1;
    uint32_t rhat = un32 - q1 * vn1;
    while (q1 >= 65536 || q1 * vn0 > ((rhat << 16) | un1)) {
        q1--; rhat += vn1;
        if (rhat >= 65536) break;
    }
    uint32_t un21 = (un32 << 16) + un1 - q1 * d;
    uint32_t q0 = un21 / vn1;
    rhat = un21 - q0 * vn1;
    while (q0 >= 65536 || q0 * vn0 > ((rhat << 16) | un0)) {
        q0--; rhat += vn1;
        if (rhat >= 65536) break;
    }
    return (q1 << 16) + q0;
}

fixed_t FixedDiv(fixed_t a, fixed_t b)
{
    int32_t aa = a < 0 ? (int32_t)(0u - (uint32_t)a) : a;   // abs() with wrap, as the original
    int32_t ab = b < 0 ? (int32_t)(0u - (uint32_t)b) : b;
    if ((aa >> 14) >= ab)
        return (a ^ b) < 0 ? INT_MIN : INT_MAX;
    uint32_t ua = a < 0 ? 0u - (uint32_t)a : (uint32_t)a;
    uint32_t ub = b < 0 ? 0u - (uint32_t)b : (uint32_t)b;
    uint32_t q;
    if (!(ua >> 16))
        q = (ua << 16) / ub;
    else if ((ua >> 14) < ub)
        q = divlu(ua >> 16, ua << 16, ub);
    else
        q = udiv_slow(ua, ub);
    return (fixed_t)((a ^ b) < 0 ? 0u - q : q);
}
