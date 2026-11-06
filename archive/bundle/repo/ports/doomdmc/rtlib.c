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
