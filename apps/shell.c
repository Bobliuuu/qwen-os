#include "qos.h"
int app_main(const qos_api *a){
 if(a->abi_version!=1)return 1;
 unsigned key=qcall(a,QOS_SYS_KEY_POLL,0,0,0);
 if(key){qputs(a,"QwenOS input: ");qcall(a,QOS_SYS_PUTC,key&255,0,0);qputs(a,"\n");}
 qputs(a,"QwenOS /bin/sh: pid ");qcall(a,QOS_SYS_PUTC,'0'+qcall(a,QOS_SYS_GETPID,0,0,0),0,0);qputs(a,"\n$ ls\n/README\n/bin/sh\n/bin/paint\n/bin/raycast\n/bin/asset\n/bin/doom\n/tmp/note\n/tmp/log\n");
 qputs(a,"$ cat /README\n");
 unsigned fd=qcall(a,QOS_SYS_OPEN,(uintptr_t)"/README",QOS_O_READ,0);
 if(fd>QOS_MAX_FD)return 2;
 char buf[100];unsigned n=qcall(a,QOS_SYS_READ,fd,(uintptr_t)buf,sizeof(buf));
 if(n>sizeof(buf))return 3;
 for(unsigned i=0;i<n;i++)qcall(a,QOS_SYS_PUTC,(uint8_t)buf[i],0,0);
 qcall(a,QOS_SYS_CLOSE,fd,0,0);
 qputs(a,"$ echo hello > /tmp/note\n");
 if(qcall(a,QOS_SYS_CREATE,(uintptr_t)"/tmp/note",0,0))return 4;
 fd=qcall(a,QOS_SYS_OPEN,(uintptr_t)"/tmp/note",QOS_O_WRITE,0);
 static const char msg[]="hello from QwenOS\n";
 if(qcall(a,QOS_SYS_WRITE,fd,(uintptr_t)msg,sizeof(msg)-1)!=sizeof(msg)-1)return 5;
 qcall(a,QOS_SYS_CLOSE,fd,0,0);
 qputs(a,"$ cat /tmp/note\n");fd=qcall(a,QOS_SYS_OPEN,(uintptr_t)"/tmp/note",QOS_O_READ,0);
 n=qcall(a,QOS_SYS_READ,fd,(uintptr_t)buf,sizeof(buf));if(n!=sizeof(msg)-1)return 6;
 for(unsigned i=0;i<n;i++)qcall(a,QOS_SYS_PUTC,(uint8_t)buf[i],0,0);
 qcall(a,QOS_SYS_CLOSE,fd,0,0);
 qputs(a,"$ run /bin/paint\n");if(qcall(a,QOS_SYS_EXEC,(uintptr_t)"/bin/paint",0,0))return 7;
 qputs(a,"$ run /bin/raycast\n");if(qcall(a,QOS_SYS_EXEC,(uintptr_t)"/bin/raycast",0,0))return 8;
 qputs(a,"$ run /bin/asset\n");(void)qcall(a,QOS_SYS_EXEC,(uintptr_t)"/bin/asset",0,0);
 qputs(a,"$ run /bin/doom\n");if(qcall(a,QOS_SYS_EXEC,(uintptr_t)"/bin/doom",0,0))return 10;
 qputs(a,"QwenOS shell finished\n");return 0;
}
