#include "qos.h"
/* Proof of an actual WAD file being read by RV32 application code through
 * the QwenOS kernel and a block-device mailbox. Not the DOOM engine. */
static unsigned load(const qos_api *api,uint32_t offset,uint8_t *buf,uint32_t n){
 uint32_t r=qcall(api,QOS_SYS_DISK_REQUEST,offset,(uintptr_t)buf,n);
 if(r!=(uint32_t)0)return 0;
 for(unsigned i=0;i<128;i++){
  r=qcall(api,QOS_SYS_DISK_POLL,0,0,0);
  if(r==n)return 1;
  if(r!=(uint32_t)0)return 0;
 }
 qcall(api,QOS_SYS_DISK_CANCEL,0,0,0);
 return 0;
}
static uint32_t rd32(const uint8_t *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
int app_main(const qos_api *a){
 uint8_t h[12],d[16],payload[32];
 if(!load(a,0,h,sizeof(h))){qputs(a,"asset: no disk device\n");return 0;}
 if(h[0]!='I'||h[1]!='W'||h[2]!='A'||h[3]!='D'||rd32(h+4)<1){qputs(a,"asset: bad WAD header\n");return 1;}
 uint32_t directory=rd32(h+8);
 if(!load(a,directory,d,sizeof(d))){qputs(a,"asset: directory unavailable\n");return 2;}
 uint32_t pos=rd32(d),sz=rd32(d+4);
 if(sz!=32||d[8]!='Q'||d[9]!='O'||d[10]!='S'||d[11]!='D'){qputs(a,"asset: invalid lump\n");return 3;}
 if(!load(a,pos,payload,sizeof(payload))){qputs(a,"asset: lump unavailable\n");return 4;}
 static const char expected[]="QwenOS paged WAD data test pass!";
 for(unsigned i=0;i<32;i++)if(payload[i]!=(uint8_t)expected[i]){qputs(a,"asset: bad lump data\n");return 5;}
 qputs(a,"asset: WAD read and verified\n");return 0;
}
