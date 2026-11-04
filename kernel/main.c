#include "qos.h"
/* Qwenputer has no S-mode, MMU or kernel traps. Guest software uses a fixed
   function-pointer ABI and all guests share a single physical address space.
   Applications are separate ROM-linked ELFs, not isolated processes. */
#define FILES 9
#define F_DOOMD 6 /* /bin/doomd: full-RAM takeover app (never nested) */
#define F_TMP0 7   /* first RAMFS file index */
#define CORE(n) __attribute__((section(".bss.core." #n)))
#define FILE_SIZE 512
#define APP_STACK_BYTES 1536u
static uint8_t app_stacks[QOS_MAX_PROC][APP_STACK_BYTES] __attribute__((aligned(16)));
extern int qos_app_call(uintptr_t entry,const qos_api *api,uintptr_t stack_top);
uint8_t qos_framebuffer[QOS_FB_W*QOS_FB_H] CORE(d_fb);
/* Normal-mode kernel stack lives in the overlay (the takeover runs on the tiny core stack, see kernel.ld). */
uint8_t qos_kstack[128] __attribute__((aligned(16),section(".bss.kstack")));
#define framebuffer qos_framebuffer
/* Firmware-visible keyboard mailbox (layout and push protocol in include/qos.h): a 4-deep ring.
 * The model/host injects keys by updating the RAM snapshot between execution bursts. */
volatile struct {uint32_t seq;uint8_t q[4];} qos_input_mailbox CORE(b_in);
/* Disk mailbox: an external data device may fill bytes while the model is
 * paused between execution steps. It cannot execute guest instructions.
 * ready_seq is written LAST by the driver after bytes and status are set. */
volatile struct {
 uint32_t request_seq,offset,length,ready_seq,status;
 uint8_t bytes[QOS_DISK_WINDOW];
} qos_disk_mailbox CORE(c_disk);
/* Resident "core" state (survives a doomd takeover); see linker/kernel.ld. */
/* ram_dirty: 1 once any program other than the shell has run (or doomd has run): application RAM beyond the
   kernel overlay may then hold garbage and the next /bin/doomd takeover must zero all of it. Packed into 20 B. */
struct{uint32_t key_seq_seen,disk_seq;uint16_t disk_dest,disk_length;uint8_t disk_active,takeover,ram_dirty,reboots,current_pid;} qos_kv CORE(a_vars);
#define key_seq_seen qos_kv.key_seq_seen
#define disk_seq qos_kv.disk_seq
#define disk_dest qos_kv.disk_dest
#define disk_length qos_kv.disk_length
#define disk_active qos_kv.disk_active
#define takeover qos_kv.takeover
#define ram_dirty qos_kv.ram_dirty
#define reboots qos_kv.reboots
#define current_pid qos_kv.current_pid
static uint32_t last_present_checksum; /* overlay: never touched while doomd runs */
extern uint32_t __ov_start[],__ov_end[];
extern int qos_main(void);
extern void qos_takeover_enter(void) __attribute__((noreturn));
extern void qos_resume_enter(void) __attribute__((noreturn));
void qos_resume(void);
static const char readme[]="QwenOS: RV32IM kernel, ROM apps, RAMFS, framebuffer, ABI v1.\n";
static const char * const file_names[FILES]={"/README","/bin/sh","/bin/paint","/bin/raycast","/bin/asset","/bin/doom","/bin/doomd","/tmp/note","/tmp/log"};
static char writable[2][FILE_SIZE];
static unsigned lengths[2];
typedef struct {unsigned used,owner,file,pos,write;} fd_t;
static fd_t fds[QOS_MAX_FD];
typedef struct {unsigned pid,parent,state,exitcode;} proc_t;
static proc_t procs[QOS_MAX_PROC];
static unsigned next_pid,proc_top,executions;
static void hw_putc(uint32_t c){register unsigned a0 asm("a0")=c;register unsigned a7 asm("a7")=1;asm volatile("ecall" : "+r"(a0):"r"(a7):"memory");}
static int streq(const char *a,const char *b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static int inside(uintptr_t a,uintptr_t n,uintptr_t lo,uintptr_t hi){return a>=lo&&a<hi&&n<=hi-a;}
static int readable(uintptr_t a,uintptr_t n){return inside(a,n,QOS_RAM_BEGIN,QOS_RAM_END)||inside(a,n,QOS_DROM_BEGIN,QOS_DROM_END);}
static int writable_addr(uintptr_t a,uintptr_t n){return inside(a,n,QOS_RAM_BEGIN,QOS_RAM_END);}
/* NUL-terminated name (<80 chars) entirely inside RAM or data ROM: one range check, then scan. */
static int name_ok(const char *s){uintptr_t p=(uintptr_t)s,hi=(p>=QOS_RAM_BEGIN&&p<QOS_RAM_END)?QOS_RAM_END:(p>=QOS_DROM_BEGIN&&p<QOS_DROM_END)?QOS_DROM_END:0;
 for(unsigned i=0;i<80&&p+i<hi;i++)if(!s[i])return 1;return 0;}
static int file_number(const char *name){if(!name_ok(name))return -1;for(int i=0;i<FILES;i++)if(streq(name,file_names[i]))return i;return -1;}
static int getfd(unsigned f){return f<QOS_MAX_FD&&fds[f].used&&fds[f].owner==current_pid;}
static unsigned sys(uint32_t n,uintptr_t a,uintptr_t b,uintptr_t c);
static unsigned sys_entry(uint32_t n,uintptr_t a,uintptr_t b,uintptr_t c);
static const qos_api api={1,sys_entry};
typedef int (*app_entry)(const qos_api*);
extern void qos_key_park(void);
static const uint32_t entries[]={QOS_SHELL_ENTRY,QOS_PAINT_ENTRY,QOS_RAY_ENTRY,QOS_ASSET_ENTRY,QOS_DOOM_ENTRY};
static int spawn_idx(int which){ /* which = file index from file_number(), or -1 */
 if(which<1||which>F_DOOMD)return -1;
 if(which==F_DOOMD)qos_takeover_enter(); /* never returns */
 uintptr_t addr=entries[which-1];
 if(proc_top>=QOS_MAX_PROC)return -2;
 if(which!=1)ram_dirty=1;
 unsigned old=current_pid,slot=proc_top++,pid=++next_pid;
 procs[slot]=(proc_t){pid,old,1,0};current_pid=pid;executions++;
 /* Each nested application gets an independent, bounded guest stack (16-byte canary at its end). */
 uint32_t *cv=(uint32_t*)(void*)app_stacks[slot];
 cv[0]=cv[1]=cv[2]=cv[3]=0xA5A5A5A5u;
 int result=qos_app_call(addr,&api,(uintptr_t)&app_stacks[slot][APP_STACK_BYTES]);
 if((cv[0]&cv[1]&cv[2]&cv[3])!=0xA5A5A5A5u||(cv[0]|cv[1]|cv[2]|cv[3])!=0xA5A5A5A5u)return -9;
 procs[slot].state=2;procs[slot].exitcode=(unsigned)result;
 for(unsigned i=0;i<QOS_MAX_FD;i++)if(fds[i].used&&fds[i].owner==pid)fds[i].used=0;
 current_pid=old;proc_top--;
 return result;
}
#ifndef QOS_LIVE
static int spawn(const char *name){return spawn_idx(file_number(name));}
#endif
static void disk_copy(void){unsigned n=disk_length;const uint8_t*sp=(const uint8_t*)qos_disk_mailbox.bytes;uint8_t*dp=(uint8_t*)(uintptr_t)disk_dest;
  if(!(((uintptr_t)dp)&3)){const uint32_t*s4=(const uint32_t*)(const void*)sp;uint32_t*d4=(uint32_t*)(void*)dp;
   for(;n>=16;n-=16){uint32_t a=s4[0],b=s4[1],c2=s4[2],d=s4[3];d4[0]=a;d4[1]=b;d4[2]=c2;d4[3]=d;s4+=4;d4+=4;}
   for(;n>=4;n-=4)*d4++=*s4++;sp=(const uint8_t*)s4;dp=(uint8_t*)d4;}
  while(n--)*dp++=*sp++;}
/* Oldest queued key or 0. key_seq_seen (core RAM) is the read count; if the device got more
   than 4 ahead, the oldest keys were overwritten and are skipped. */
static unsigned key_get(void){
 uint32_t s=qos_input_mailbox.seq,r=key_seq_seen;
 if(s==r)return 0;
 if(s-r>4)r=s-4;
 key_seq_seen=r+1;
 return qos_input_mailbox.q[r&3];
}
static unsigned key_wait(void){unsigned k;while(!(k=key_get()))qos_key_park();return k;}
__attribute__((noinline)) static unsigned sys(uint32_t n,uintptr_t a,uintptr_t b,uintptr_t c){
 /* While /bin/doomd owns RAM, the RAMFS/fd/proc tables are gone: only the
    core syscalls (console, fb, keys, disk, pid, yield) are available. */
 if(takeover)switch(n){
  case QOS_SYS_PUTC:case QOS_SYS_FB_SET:case QOS_SYS_FB_CLEAR:case QOS_SYS_FB_GET:
  case QOS_SYS_FB_ROW:case QOS_SYS_FB_PRESENT:case QOS_SYS_KEY_POLL:case QOS_SYS_DISK_REQUEST:
  case QOS_SYS_DISK_POLL:case QOS_SYS_DISK_CANCEL:case QOS_SYS_GETPID:case QOS_SYS_YIELD:case QOS_SYS_KEY_WAIT:case QOS_SYS_FB_PTR:break;
  default:return (unsigned)-1;
 }
 switch(n){
 case QOS_SYS_PUTC:hw_putc((uint8_t)a);return 0;
 case QOS_SYS_OPEN: {int file=file_number((const char*)a);if(file<0)return (unsigned)-1;
  if(b==QOS_O_WRITE&&file<F_TMP0)return (unsigned)-2;
  for(unsigned i=0;i<QOS_MAX_FD;i++)if(!fds[i].used){fds[i]=(fd_t){1,current_pid,(unsigned)file,0,(unsigned)b};return i;}return (unsigned)-3;}
 case QOS_SYS_READ: {unsigned fd=(unsigned)a,len=(unsigned)c;if(!getfd(fd)||!writable_addr(b,len))return (unsigned)-1;
  fd_t *f=&fds[fd];if(f->write)return (unsigned)-2;
  const char *data=0;unsigned total=0;
  if(f->file==0){data=readme;total=sizeof(readme)-1;}
  if(f->file>=F_TMP0){unsigned k=f->file-F_TMP0;data=writable[k];total=lengths[k];}
  if(!data)return 0;
  if(f->pos>=total)return 0;unsigned avail=total-f->pos;if(len>avail)len=avail;
  for(unsigned i=0;i<len;i++)((char*)b)[i]=data[f->pos+i];f->pos+=len;return len;}
 case QOS_SYS_CLOSE:if(!getfd((unsigned)a))return (unsigned)-1;fds[a].used=0;return 0;
 case QOS_SYS_CREATE: {int file=file_number((const char*)a);if(file<F_TMP0)return (unsigned)-1;lengths[file-F_TMP0]=0;return 0;}
 case QOS_SYS_WRITE:{unsigned fd=(unsigned)a,len=(unsigned)c;if(!getfd(fd)||!readable(b,len))return (unsigned)-1;
  fd_t *f=&fds[fd];if(!f->write||f->file<F_TMP0)return (unsigned)-2;
  unsigned k=f->file-F_TMP0;if(f->pos>FILE_SIZE)return (unsigned)-3;
  if(len>FILE_SIZE-f->pos)len=FILE_SIZE-f->pos;
  for(unsigned i=0;i<len;i++)writable[k][f->pos+i]=((const char*)b)[i];f->pos+=len;
  if(f->pos>lengths[k])lengths[k]=f->pos;return len;}
 case QOS_SYS_EXEC:return (unsigned)spawn_idx(file_number((const char*)a));
 case QOS_SYS_FB_SET:if(a>=QOS_FB_W||b>=QOS_FB_H)return (unsigned)-1;framebuffer[b*QOS_FB_W+a]=(uint8_t)c;return 0;
 case QOS_SYS_FB_CLEAR:for(unsigned i=0;i<sizeof(framebuffer);i++)framebuffer[i]=(uint8_t)a;return 0;
 case QOS_SYS_STAT:{int f=file_number((const char*)a);if(f<0)return (unsigned)-1;if(f==0)return sizeof(readme)-1;if(f>=F_TMP0)return lengths[f-F_TMP0];return 0;}
 case QOS_SYS_GETPID:return current_pid;
 case QOS_SYS_YIELD:return 0; /* No hardware timer: cooperative execution only. */
 case QOS_SYS_FB_GET:if(a>=QOS_FB_W||b>=QOS_FB_H)return (unsigned)-1;return framebuffer[b*QOS_FB_W+a];
 case QOS_SYS_PS:return executions;
 case QOS_SYS_FB_ROW:{
  if(a>=QOS_FB_H || c!=QOS_FB_W || !readable(b,c))return (unsigned)-1;
  for(unsigned i=0;i<QOS_FB_W;i++)framebuffer[a*QOS_FB_W+i]=((const uint8_t *)b)[i];
  return 0;
 }
 case QOS_SYS_FB_PRESENT:{
  uint32_t hash=2166136261u;
  for(unsigned i=0;i<sizeof(framebuffer);i++)hash=(hash^framebuffer[i])*16777619u;
  last_present_checksum=hash;
  return hash;
 }
 case QOS_SYS_DISK_CANCEL:
  disk_active=0;return 0;
 case QOS_SYS_DISK_REQUEST:
  if(disk_active || c==0 || c>QOS_DISK_WINDOW || !writable_addr(b,c) || a>0xffffffffu-c)
   return (unsigned)-1;
  disk_dest=(uint32_t)b;disk_length=(uint32_t)c;disk_active=1;
  disk_seq=qos_disk_mailbox.request_seq+1; /* the mailbox is the sequence authority (takeover code writes it directly) */
  qos_disk_mailbox.offset=(uint32_t)a;
  qos_disk_mailbox.length=(uint32_t)c;
  qos_disk_mailbox.status=0;
  qos_disk_mailbox.request_seq=disk_seq; /* publish LAST */
  return 0;
 case QOS_SYS_DISK_POLL:
  if(!disk_active)return (unsigned)-1;
  if(qos_disk_mailbox.ready_seq!=disk_seq)return 0;
  if(qos_disk_mailbox.status!=1){disk_active=0;return (unsigned)-2;}
  disk_copy();
  disk_active=0;
  return disk_length;
 case QOS_SYS_KEY_POLL:return key_get();
 case QOS_SYS_KEY_WAIT:return key_wait();
 case QOS_SYS_FB_PTR:return (unsigned)(uintptr_t)framebuffer; /* apps may write pixels (row-major, QOS_FB_W*QOS_FB_H bytes) directly */

 default:return (unsigned)-1;
 }
}
/* API entry. DISK_READ = request + bounded wait + copy in one call (the hot path of DOOM's NOR reads);
   everything else is sys(). The host services the mailbox exactly as for DISK_REQUEST/DISK_POLL. */
__attribute__((noinline)) static unsigned disk_read(uintptr_t a,uintptr_t b,uintptr_t c){
 if(disk_active||c-1u>=QOS_DISK_WINDOW||b<QOS_RAM_BEGIN||b>QOS_RAM_END-c||a>0xffffffffu-c)return (unsigned)-1;
 uint32_t seq=qos_disk_mailbox.request_seq+1;disk_seq=seq;
 qos_disk_mailbox.offset=(uint32_t)a;qos_disk_mailbox.length=(uint32_t)c;qos_disk_mailbox.status=0;
 qos_disk_mailbox.request_seq=seq;
 if(qos_disk_mailbox.ready_seq!=seq){
  disk_dest=(uint32_t)b;disk_length=(uint32_t)c;disk_active=1;
  for(unsigned i=0;i<4096;i++)if(qos_disk_mailbox.ready_seq==seq)goto ready;
  return 0; /* still pending: caller continues with DISK_POLL */
 }
 ready:
 if(qos_disk_mailbox.status!=1){disk_active=0;return (unsigned)-2;}
 {const uint32_t*sp=(const uint32_t*)(const void*)qos_disk_mailbox.bytes;uint32_t*dp=(uint32_t*)b;unsigned w=(unsigned)c>>2;
  if(!((b|c)&3)){for(;w>=4;w-=4){uint32_t x0=sp[0],x1=sp[1],x2=sp[2],x3=sp[3];dp[0]=x0;dp[1]=x1;dp[2]=x2;dp[3]=x3;sp+=4;dp+=4;}
   while(w--)*dp++=*sp++;}
  else{ /* unaligned destination or odd length: word loads from the mailbox, byte stores (little endian) */
   uint8_t*d1=(uint8_t*)b;unsigned n=(unsigned)c;
   for(;n>=8;n-=8){uint32_t x=sp[0],y=sp[1];
    d1[0]=(uint8_t)x;d1[1]=(uint8_t)(x>>8);d1[2]=(uint8_t)(x>>16);d1[3]=(uint8_t)(x>>24);
    d1[4]=(uint8_t)y;d1[5]=(uint8_t)(y>>8);d1[6]=(uint8_t)(y>>16);d1[7]=(uint8_t)(y>>24);sp+=2;d1+=8;}
   if(n){uint32_t x=sp[0];sp++;
    if(n>=4){d1[0]=(uint8_t)x;d1[1]=(uint8_t)(x>>8);d1[2]=(uint8_t)(x>>16);d1[3]=(uint8_t)(x>>24);d1+=4;n-=4;if(n)x=sp[0];}
    switch(n){case 3:d1[2]=(uint8_t)(x>>16);/* fallthrough */case 2:d1[1]=(uint8_t)(x>>8);/* fallthrough */case 1:d1[0]=(uint8_t)x;}}}}
 disk_active=0;
 return (unsigned)c;
}
/* hot paths first, each as a leaf/tail call so they pay no big prologue */
static unsigned sys_entry(uint32_t n,uintptr_t a,uintptr_t b,uintptr_t c){
 if(n==QOS_SYS_PUTC){hw_putc((uint8_t)a);return 0;}
 if(n==QOS_SYS_DISK_READ)return disk_read(a,b,c);
 if(n==QOS_SYS_KEY_WAIT)return key_wait();
 return sys(n,a,b,c);
}
/* Takeover entry (kernel stack, reached via qos_takeover_enter in start.S).
 * The shell/RAMFS overlay is abandoned, doomd runs on a stack at the very top
 * of RAM, and when it returns the overlay is zeroed and the OS warm-reboots
 * (RAMFS contents are NOT preserved). Core mailboxes/fb keep their contents. */
#ifdef QOS_MODEL_BRIDGE
/* The park/resume probe must stay tiny (see model_probe_ref): no takeover. */
void qos_takeover_run(void){for(;;);}
void qos_resume(void){for(;;);}
#else
/* Zero [lo,hi) (16-byte units, 4 stores per loop trip). */
static void zero_ram(uint32_t *p,uintptr_t hi){for(uint32_t *e=(uint32_t*)((hi+15)&~15u);p<e;p+=4)p[0]=p[1]=p[2]=p[3]=0;}
void qos_takeover_run(void){
 /* Contract with /bin/doomd (apps/doomd_crt0.S, doomd_main): all of RAM from QOS_DOOMD_RAM_BASE up is ZERO on
    entry. Only the kernel overlay is dirty after a shell-only session (4.4 KB); after other apps or a previous
    doomd run everything may be, so clear it all. */
 zero_ram(ram_dirty?(uint32_t*)QOS_DOOMD_RAM_BASE:__ov_start,ram_dirty?QOS_RAM_END:(uintptr_t)__ov_end);
 ram_dirty=1;
 takeover=1;current_pid=2;disk_active=0;
 qos_app_call(QOS_DOOMD_ENTRY,&api,QOS_RAM_END);
 takeover=0;disk_active=0;key_seq_seen=qos_input_mailbox.seq;reboots++;current_pid=0;
 zero_ram(__ov_start,(uintptr_t)__ov_end);
 qos_resume_enter(); /* onto the (zeroed) overlay kernel stack, calls qos_resume */
}
void qos_resume(void){
 const char *s="QWENOS_DOOMD_EXIT\n";while(*s)hw_putc((uint8_t)*s++);
 register unsigned a0 asm("a0")=(unsigned)qos_main(),a7 asm("a7")=93;
 asm volatile("ecall" : "+r"(a0):"r"(a7):"memory");
 for(;;);
}
#endif
#ifdef QOS_MODEL_BRIDGE
/* Qwenputer's merged model starts with the firmware PARKED at its first exit
 * ecall. When a Qwen tool call produces GO, the instruction immediately after
 * that ecall resumes. This probe uses the SAME kernel syscalls as the full OS,
 * but intentionally avoids its expensive and asynchronous disk workload.
 * a0=256/257 emits bridge-special <tool_response> tags, not ordinary bytes.
 */
int qos_main(void){
 register uint32_t a0 asm("a0")=0, a7 asm("a7")=93;
 asm volatile("ecall" : "+r"(a0) : "r"(a7) : "memory");
 hw_putc(256u);
 if(api.abi_version!=1u || sys(QOS_SYS_FB_SET,3,4,7)!=0u ||
    sys(QOS_SYS_FB_GET,3,4,0)!=7u ||
    sys(QOS_SYS_GETPID,0,0,0)!=0u){
  const char *p="QWENOS_MODEL_PROBE_FAIL\n";
  while(*p)hw_putc((uint8_t)*p++);
  hw_putc(257u);
  return 5;
 }
 const char *p="QWENOS_MODEL_PROBE_OK\n";
 while(*p)hw_putc((uint8_t)*p++);
 hw_putc(257u);
 return 0;
}
#else
#ifdef QOS_LIVE
/* Live mode: no banner, no boot script. The shell (apps/shell.c, SHELL_LIVE) prints its prompt and
 * reads typed keys from the keyboard mailbox; it returns only on `exit`. After a /bin/doomd
 * takeover returns, the warm reboot lands here again and the prompt comes back. */
int qos_main(void){return spawn_idx(1);}
#else
int qos_main(void){
 const char *s="QwenOS: Qwenputer RV32IM kernel\n";while(*s)hw_putc(*s++);
 int rc=spawn("/bin/sh");
 if(rc||executions!=5||last_present_checksum==0)return 8;
 s="QWENOS_BOOT_OK\n";while(*s)hw_putc(*s++);
#ifdef QOS_BOOT_DOOMD
 if(!reboots){s="QWENOS_DOOMD_BOOT\n";while(*s)hw_putc(*s++);spawn("/bin/doomd");return 9;}
#endif
 return 0;
}

#endif /* QOS_LIVE */
#endif /* QOS_MODEL_BRIDGE */
