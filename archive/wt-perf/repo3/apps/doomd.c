/* Stub /bin/doomd: exercises the takeover contract (whole app RAM writable,
   .data/.bss init by crt0, core syscalls, restricted syscalls). The real
   engine replaces this file's role; keep the crt0 + linker/doomd.ld contract. */
#include "qos.h"
extern uint32_t __bss_end[],__stack_limit[],__app_ram_start[];
static volatile uint32_t magic=0x1234abcdu;
static volatile uint32_t zeroed;
static void num(const qos_api *a,uint32_t v){char t[10];int n=0;do{t[n++]='0'+v%10;v/=10;}while(v);while(n)qcall(a,QOS_SYS_PUTC,t[--n],0,0);}
int doomd_main(const qos_api *a){
 if(a->abi_version!=1)return 1;
 if(magic!=0x1234abcdu||zeroed)return 2;
 qputs(a,"doomd: takeover\n");
 /* No RAMFS under takeover: file syscalls must fail cleanly. */
 if(qcall(a,QOS_SYS_OPEN,(uintptr_t)"/README",QOS_O_READ,0)!=(uint32_t)-1)return 3;
 /* Every free word of the app RAM (everything kernel/shell used to own). */
 uint32_t *lo=__bss_end,*hi=__stack_limit;
 for(uint32_t *p=lo;p<hi;p++)*p=(uint32_t)(uintptr_t)p*2654435761u;
 for(uint32_t *p=lo;p<hi;p++)if(*p!=(uint32_t)(uintptr_t)p*2654435761u)return 4;
 qputs(a,"doomd: free RAM words ");num(a,(uint32_t)(hi-lo));qputs(a,"\n");
 qputs(a,"doomd: app RAM base ");num(a,(uint32_t)(uintptr_t)__app_ram_start);qputs(a,"\n");
 uint8_t row[QOS_FB_W];
 for(unsigned y=0;y<QOS_FB_H;y++){
  for(unsigned x=0;x<QOS_FB_W;x++)row[x]=(uint8_t)(x*8+y);
  if(qcall(a,QOS_SYS_FB_ROW,y,(uintptr_t)row,QOS_FB_W))return 5;
 }
 if(!qcall(a,QOS_SYS_FB_PRESENT,0,0,0))return 6;
 if(qcall(a,QOS_SYS_DISK_REQUEST,0,(uintptr_t)row,16))return 7;
 qcall(a,QOS_SYS_DISK_CANCEL,0,0,0);
 (void)qcall(a,QOS_SYS_KEY_POLL,0,0,0);
 qputs(a,"DOOMD_STUB_OK\n");
 return 0;
}
