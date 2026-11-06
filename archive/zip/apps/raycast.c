#include "qos.h"
/* A fixed-point pseudo-3D graphics proof, NOT DOOM. The wall height follows
   a distance-like profile; no floating point, framebuffer MMIO or host renderer. */
int app_main(const qos_api *a){
 qcall(a,QOS_SYS_FB_CLEAR,0,0,0);
 /* Buffer complete rows before sending them to the kernel; future DOOM
    strip renderers can use the same interface without a full 320x200 buffer. */
 uint8_t rows[QOS_FB_H][QOS_FB_W];
 /* The device mailbox supplies discrete actions for the demo; this establishes
    input-to-frame causality in guest code. DOOM will use the same poll ABI. */
 unsigned key=qcall(a,QOS_SYS_KEY_POLL,0,0,0);
 unsigned center=key=='d'?19:(key=='a'?11:15);
 for(unsigned x=0;x<QOS_FB_W;x++){
  unsigned dx=x>center?x-center:center-x;
  unsigned wall=18-(dx*12/16);
  unsigned top=(QOS_FB_H-wall)/2;
  for(unsigned y=0;y<QOS_FB_H;y++){
   unsigned shade=y<top?1:(y<top+wall?9:3);
   if((y>=top && y<top+wall) && (x==7||x==24))shade=7;
   rows[y][x]=(uint8_t)shade;
  }
 }
 for(unsigned y=0;y<QOS_FB_H;y++)
  if(qcall(a,QOS_SYS_FB_ROW,y,(uintptr_t)rows[y],QOS_FB_W)!=0)return 3;
 if(qcall(a,QOS_SYS_FB_PRESENT,0,0,0)==0)return 4;
 if(qcall(a,QOS_SYS_FB_GET,0,0,0)!=1)return 1;
 if(qcall(a,QOS_SYS_FB_GET,center,12,0)!=9)return 2;
 qputs(a,"raycast: frame rendered\n");return 0;
}
