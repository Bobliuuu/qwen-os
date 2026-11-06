#include "hal.h"
/* All guest code runs as RV32IM instructions. External storage only transfers
 * data through QwenOS's mailbox. No host-side WAD interpretation is needed. */
int qos_doom_wad_read(const qos_api *api,uint32_t offset,void *dst,unsigned n){
 uint8_t *out=(uint8_t*)dst;
 if(!api||api->abi_version!=1||(!dst&&n)||n>0xffffffffu-offset)return 0;
 while(n){
  unsigned count=n>QOS_DISK_WINDOW?QOS_DISK_WINDOW:n;
  if(qcall(api,QOS_SYS_DISK_REQUEST,offset,(uintptr_t)out,count))return 0;
  unsigned ok=0;
  for(unsigned j=0;j<16;j++){
   uint32_t r=qcall(api,QOS_SYS_DISK_POLL,0,0,0);
   if(r==count){ok=1;break;}
   if(r){qcall(api,QOS_SYS_DISK_CANCEL,0,0,0);return 0;}
  }
  if(!ok){qcall(api,QOS_SYS_DISK_CANCEL,0,0,0);return 0;}
  offset+=count;out+=count;n-=count;
 }
 return 1;
}
int qos_doom_present8(const qos_api *api,const uint8_t *pixels){
 if(!api||api->abi_version!=1||!pixels)return 0;
 for(unsigned y=0;y<QOS_FB_H;y++)
  if(qcall(api,QOS_SYS_FB_ROW,y,(uintptr_t)(pixels+y*QOS_FB_W),QOS_FB_W))return 0;
 return qcall(api,QOS_SYS_FB_PRESENT,0,0,0)!=0;
}
unsigned qos_doom_key(const qos_api *api){
 return (api&&api->abi_version==1)?qcall(api,QOS_SYS_KEY_POLL,0,0,0):0;
}
