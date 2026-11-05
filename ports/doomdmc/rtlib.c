/* Minimal compiler runtime for RV32IM (no F/D, no 64-bit div in HW). */
#include <stdint.h>
uint64_t __udivmoddi4(uint64_t n,uint64_t d,uint64_t*r){
 uint64_t q=0,rem=0;
 for(int i=63;i>=0;i--){rem=(rem<<1)|((n>>i)&1);if(rem>=d){rem-=d;q|=1ull<<i;}}
 if(r)*r=rem;return q;}
uint64_t __udivdi3(uint64_t n,uint64_t d){return __udivmoddi4(n,d,0);}
uint64_t __umoddi3(uint64_t n,uint64_t d){uint64_t r;__udivmoddi4(n,d,&r);return r;}
int64_t __divdi3(int64_t n,int64_t d){int neg=(n<0)^(d<0);uint64_t q=__udivmoddi4(n<0?-n:n,d<0?-d:d,0);return neg?-(int64_t)q:(int64_t)q;}
int64_t __moddi3(int64_t n,int64_t d){uint64_t r;__udivmoddi4(n<0?-n:n,d<0?-d:d,&r);return n<0?-(int64_t)r:(int64_t)r;}
uint64_t __ashldi3(uint64_t a,int b){return b&32?(uint64_t)(uint32_t)a<<(b&31)<<32:b?(a<<b):a;}
uint64_t __lshrdi3(uint64_t a,int b){return b&32?(a>>32)>>(b&31):b?(a>>b):a;}
int64_t __ashrdi3(int64_t a,int b){return a>>b;}
/* Float is only reached from the demo timing printout (G_CheckDemoStatus) and the mouse-speed debug box;
   both are stripped in a real port. Stubs keep the link honest but are never meant to run. */
float __addsf3(float a,float b){(void)a;(void)b;return 0;}
float __mulsf3(float a,float b){(void)a;(void)b;return 0;}
float __divsf3(float a,float b){(void)a;(void)b;return 0;}
float __floatsisf(int a){(void)a;return 0;}
int __fixsfsi(float a){(void)a;return 0;}
double __extendsfdf2(float a){(void)a;return 0;}
int __ltdf2(double a,double b){return a<b;}

/* ---- memcpy / memset / memmove: strong versions replacing the WEAK byte/word loops of platform/rt.c ----
   Same results for every input (non-overlapping memcpy; memmove falls back to the backward byte loop for the
   overlapping-forward case), 16 bytes per loop turn when aligned, word access when src and dst share their
   alignment. Built with -fno-builtin-memcpy/-memset (build.sh CF_rtlib) so clang cannot turn the loops into calls. */
#include <stddef.h>
void *memcpy(void *restrict d, const void *restrict s, size_t n)
{
    uint8_t *p = d; const uint8_t *q = s;
    if (n >= 8 && !(((uintptr_t)p ^ (uintptr_t)q) & 3u)) {
        while ((uintptr_t)p & 3u) { *p++ = *q++; n--; }
        uint32_t *pw = (uint32_t *)(void *)p; const uint32_t *qw = (const uint32_t *)(const void *)q;
        for (; n >= 16; n -= 16, pw += 4, qw += 4) {
            uint32_t a = qw[0], b = qw[1], c = qw[2], e = qw[3];
            pw[0] = a; pw[1] = b; pw[2] = c; pw[3] = e;
        }
        for (; n >= 4; n -= 4) *pw++ = *qw++;
        p = (uint8_t *)pw; q = (const uint8_t *)qw;
    }
    while (n--) *p++ = *q++;
    return d;
}
void *memmove(void *d, const void *s, size_t n)
{
    uint8_t *p = d; const uint8_t *q = s;
    if (p <= q || p >= q + n) return memcpy(d, s, n);
    while (n--) p[n] = q[n];
    return d;
}
void *memset(void *d, int c, size_t n)
{
    uint8_t *p = d;
    if (n >= 4 && !((uintptr_t)p & 3u)) {
        uint32_t v = (uint8_t)c * 0x01010101u;
        uint32_t *pw = (uint32_t *)(void *)p;
        for (; n >= 16; n -= 16, pw += 4) { pw[0] = v; pw[1] = v; pw[2] = v; pw[3] = v; }
        for (; n >= 4; n -= 4) *pw++ = v;
        p = (uint8_t *)pw;
    }
    while (n--) *p++ = (uint8_t)c;
    return d;
}
