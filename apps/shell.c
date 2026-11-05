#ifdef SHELL_LIVE
/* Interactive shell: reads typed keys from the keyboard mailbox (KEY_WAIT parks the guest until
 * the device injects a key), echoes them, handles backspace/Enter and runs ls, cat, echo [> file],
 * run /bin/X, help, doom (= run /bin/doomd), exit. ~1.3 KiB; must stay inside its 4 KiB ROM slot. */
#include "qos.h"
#define PC(c) qcall(a,QOS_SYS_PUTC,(c),0,0)
static void ps(const qos_api *a,const char *s){while(*s)PC((uint8_t)*s++);}
static int eq(const char *x,const char *y){while(*x&&*x==*y){x++;y++;}return *x==*y;}
static void say(const qos_api *a,unsigned fd,const char *s){
 if(fd==~0u){ps(a,s);return;}
 unsigned n=0;while(s[n])n++;
 qcall(a,QOS_SYS_WRITE,fd,(uintptr_t)s,n);
}
int app_main(const qos_api *a){
 char line[64],blk[48];char *av[8];
 for(;;){
  ps(a,"$ ");
  unsigned n=0,c;
  for(;;){
   c=qcall(a,QOS_SYS_KEY_WAIT,0,0,0);
   if(c=='\n'||c=='\r')break;
   if(c==8||c==127){if(n){n--;ps(a,"\b \b");}}
   else if(c>=32&&n<sizeof line-1){line[n++]=(char)c;PC(c);}
  }
  PC('\n');line[n]=0;
  unsigned ac=0;
  for(char *p=line;*p;){
   while(*p==' ')*p++=0;
   if(*p&&ac<8){av[ac++]=p;while(*p&&*p!=' ')p++;}
  }
  if(!ac)continue;
  const char *cmd=av[0];
  if(eq(cmd,"ls"))ps(a,"/README\n/bin/sh\n/bin/paint\n/bin/raycast\n/bin/asset\n/bin/doom\n/bin/doomd\n/tmp/note\n/tmp/log\n");
  else if(eq(cmd,"cat")&&ac>1){
   unsigned fd=qcall(a,QOS_SYS_OPEN,(uintptr_t)av[1],QOS_O_READ,0);
   if(fd>QOS_MAX_FD){ps(a,"?\n");continue;}
   unsigned r;while((r=qcall(a,QOS_SYS_READ,fd,(uintptr_t)blk,sizeof blk))&&r<=sizeof blk)for(unsigned i=0;i<r;i++)PC((uint8_t)blk[i]);
   qcall(a,QOS_SYS_CLOSE,fd,0,0);
  }
  else if(eq(cmd,"echo")){
   unsigned k=1,fd=~0u;
   while(k<ac&&!eq(av[k],">"))k++;
   if(k+1<ac){ /* echo ... > file */
    if(qcall(a,QOS_SYS_CREATE,(uintptr_t)av[k+1],0,0)||(fd=qcall(a,QOS_SYS_OPEN,(uintptr_t)av[k+1],QOS_O_WRITE,0))>QOS_MAX_FD){ps(a,"?\n");continue;}
   }
   for(unsigned i=1;i<k;i++){if(i>1)say(a,fd," ");say(a,fd,av[i]);}
   say(a,fd,"\n");
   if(fd!=~0u)qcall(a,QOS_SYS_CLOSE,fd,0,0);
  }
  else if(eq(cmd,"help"))ps(a,"ls cat echo [> f] run /bin/X doom exit\n");
  else if(eq(cmd,"doom")){if(qcall(a,QOS_SYS_EXEC,(uintptr_t)"/bin/doomd",0,0)==~0u)ps(a,"?\n");}
  else if(eq(cmd,"run")&&ac>1){if(qcall(a,QOS_SYS_EXEC,(uintptr_t)av[1],0,0)==~0u)ps(a,"?\n");}
  else if(eq(cmd,"exit"))return 0;
  else ps(a,"?\n");
 }
}
#else
#include "qos.h"
int app_main(const qos_api *a){
 if(a->abi_version!=1)return 1;
 unsigned key=qcall(a,QOS_SYS_KEY_POLL,0,0,0);
 if(key){qputs(a,"QwenOS input: ");qcall(a,QOS_SYS_PUTC,key&255,0,0);qputs(a,"\n");}
 qputs(a,"QwenOS /bin/sh: pid ");qcall(a,QOS_SYS_PUTC,'0'+qcall(a,QOS_SYS_GETPID,0,0,0),0,0);qputs(a,"\n$ ls\n/README\n/bin/sh\n/bin/paint\n/bin/raycast\n/bin/asset\n/bin/doom\n/bin/doomd\n/tmp/note\n/tmp/log\n");
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
#endif
