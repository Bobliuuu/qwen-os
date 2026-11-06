#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <limits.h>
typedef int32_t fixed_t;
#define main_old 1
static uint32_t UDivFixO(uint32_t ua, uint32_t ub){uint32_t r,n,q=0;int i;if((ua>>14)<ub){r=ua>>14;n=ua<<18;i=30;}else{r=0;n=ua;i=48;}while(i--){r=(r<<1)|(n>>31);n<<=1;q<<=1;if(r>=ub){r-=ub;q|=1;}}return q;}
static fixed_t FDold(fixed_t a,fixed_t b){if((abs(a)>>14)>=abs(b))return (a^b)<0?INT_MIN:INT_MAX;uint32_t ua=a<0?0u-(uint32_t)a:(uint32_t)a,ub=b<0?0u-(uint32_t)b:(uint32_t)b;uint32_t q=UDivFixO(ua,ub);return (fixed_t)((a^b)<0?0u-q:q);}
#define FixedDiv FixedDiv_new
#define UDivFix UDivFixO
#include "fdtest.inc"
int main(){srand(1);long bad=0;for(long i=0;i<200000000;i++){uint32_t r1=((uint32_t)rand()<<16)^rand()^((uint32_t)rand()<<31),r2=((uint32_t)rand()<<16)^rand()^((uint32_t)rand()<<31);
 int sa=rand()%32,sb=rand()%32;int32_t a=(int32_t)(r1>>sa),b=(int32_t)(r2>>sb);if(rand()%4==0)a=-a;if(rand()%4==0)b=-b;
 if(i<100)a=(i%7==0)?INT_MIN:a; if(i%1000==0){b=rand()%5-2;}
 if(FDold(a,b)!=FixedDiv_new(a,b)){if(bad++<5)printf("BAD %d %d: %d %d\n",a,b,FDold(a,b),FixedDiv_new(a,b));}}
 printf("bad=%ld\n",bad);}
