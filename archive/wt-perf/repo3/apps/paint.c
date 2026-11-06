#include "qos.h"
int app_main(const qos_api *a){
 for(unsigned y=0;y<QOS_FB_H;y++)for(unsigned x=0;x<QOS_FB_W;x++)
  if(qcall(a,QOS_SYS_FB_SET,x,y,(x^y)&255))return 1;
 qputs(a,"paint: framebuffer changed\n");return 0;
}
