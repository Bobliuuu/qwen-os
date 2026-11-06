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
/* The framebuffer lives in the (destroyable) overlay: while /bin/doomd owns RAM the
   FB syscalls stream to the console as 0x01 'V'/'H'/'K' packets instead (see sys()). */
static uint8_t framebuffer[QOS_FB_W*QOS_FB_H];
/* Normal-mode kernel stack (overlay). The takeover runs on a tiny stack in the core. */
uint8_t qos_kstack[128] __attribute__((aligned(16),section(".bss.kstack")));
/* Firmware-visible mailbox. The model may inject external device events by
 * updating the RAM snapshot between execution bursts. Not a hardware keyboard.
 * seq is written LAST by the device driver; key code 0 means no event. */
volatile struct {uint32_t seq,key;} qos_input_mailbox CORE(b_in);
/* Disk mailbox: an external data device may fill bytes while the model is
 * paused between execution steps. It cannot execute guest instructions.
 * ready_seq is written LAST by the driver after bytes and status are set. */
volatile struct {
 uint32_t request_seq,offset,length,ready_seq,status;
 uint8_t bytes[QOS_DISK_WINDOW]; /* only QOS_DISK_TAKEOVER_WINDOW bytes are resident while doomd runs */
} qos_disk_mailbox CORE(e_disk);
/* Resident "core" state (survives a doomd takeover); see linker/kernel.ld. */
static struct {uint32_t key_seq_seen;uint16_t disk_dest,disk_length;uint8_t disk_active,takeover,reboots,current_pid;} cv CORE(a_vars);
#define key_seq_seen cv.key_seq_seen
#define disk_dest cv.disk_dest
#define disk_length cv.disk_length
#define disk_active cv.disk_active
#define takeover cv.takeover
#define reboots cv.reboots
#define current_pid cv.current_pid
static uint32_t last_present_checksum; /* overlay: never touched while doomd runs */
extern uint32_t __ov_start[],__ov_end[];
extern int qos_main(void);
extern void qos_takeover_enter(void) __attribute__((noreturn));
extern void qos_resume_enter(void) __attribute__((noreturn));
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
/* FB stream while doomd owns RAM: 0x01 kind x y n then n bytes. 'V' = n samples down column x
   from row y, 'H' = n samples along row y from column x, 'K' c = clear. Host rebuilds 32x24. */
static void fb_pkt(unsigned kind,unsigned x,unsigned y,const uint8_t *p,unsigned n){
 hw_putc(1);hw_putc(kind);hw_putc(x);hw_putc(y);hw_putc(n);
 for(unsigned i=0;i<n;i++)hw_putc(p[i]);
}
static int streq(const char *a,const char *b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static int inside(uintptr_t a,uintptr_t n,uintptr_t lo,uintptr_t hi){return a>=lo&&a<hi&&n<=hi-a;}
static int readable(uintptr_t a,uintptr_t n){return inside(a,n,QOS_RAM_BEGIN,QOS_RAM_END)||inside(a,n,QOS_DROM_BEGIN,QOS_DROM_END);}
static int writable_addr(uintptr_t a,uintptr_t n){return inside(a,n,QOS_RAM_BEGIN,QOS_RAM_END);}
static int name_ok(const char *s){uintptr_t p=(uintptr_t)s;for(unsigned i=0;i<80;i++){if(!readable(p+i,1))return 0;if(!s[i])return 1;}return 0;}
static int file_number(const char *name){if(!name_ok(name))return -1;for(int i=0;i<FILES;i++)if(streq(name,file_names[i]))return i;return -1;}
static int getfd(unsigned f){return f<QOS_MAX_FD&&fds[f].used&&fds[f].owner==current_pid;}
static unsigned sys(uint32_t n,uintptr_t a,uintptr_t b,uintptr_t c);
static const qos_api api={1,sys};
typedef int (*app_entry)(const qos_api*);
static int spawn(const char *name){
 int which=file_number(name);uintptr_t addr;
 if(which==1)addr=QOS_SHELL_ENTRY;
 else if(which==2)addr=QOS_PAINT_ENTRY;
 else if(which==3)addr=QOS_RAY_ENTRY;
 else if(which==4)addr=QOS_ASSET_ENTRY;
 else if(which==5)addr=QOS_DOOM_ENTRY;
 else if(which==F_DOOMD)qos_takeover_enter(); /* never returns */
 else return -1;
 if(proc_top>=QOS_MAX_PROC)return -2;
 unsigned old=current_pid,slot=proc_top++,pid=++next_pid;
 procs[slot]=(proc_t){pid,old,1,0};current_pid=pid;executions++;
 /* Each nested application gets an independent, bounded guest stack. */
 for(unsigned i=0;i<16;i++)app_stacks[slot][i]=0xA5;
 int result=qos_app_call(addr,&api,(uintptr_t)&app_stacks[slot][APP_STACK_BYTES]);
 for(unsigned i=0;i<16;i++)if(app_stacks[slot][i]!=0xA5)return -9;
 procs[slot].state=2;procs[slot].exitcode=(unsigned)result;
 for(unsigned i=0;i<QOS_MAX_FD;i++)if(fds[i].used&&fds[i].owner==pid)fds[i].used=0;
 current_pid=old;proc_top--;
 return result;
}
static unsigned sys(uint32_t n,uintptr_t a,uintptr_t b,uintptr_t c){
 /* While /bin/doomd owns RAM, the RAMFS/fd/proc tables are gone: only the
    core syscalls (console, fb, keys, disk, pid, yield) are available. */
 if(takeover)switch(n){
  case QOS_SYS_PUTC:case QOS_SYS_FB_SET:case QOS_SYS_FB_CLEAR:case QOS_SYS_FB_GET:case QOS_SYS_FB_COL:
  case QOS_SYS_FB_ROW:case QOS_SYS_FB_PRESENT:case QOS_SYS_KEY_POLL:case QOS_SYS_DISK_REQUEST:
  case QOS_SYS_DISK_POLL:case QOS_SYS_DISK_CANCEL:case QOS_SYS_GETPID:case QOS_SYS_YIELD:break;
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
 case QOS_SYS_EXEC:if(!name_ok((const char*)a))return (unsigned)-1;return (unsigned)spawn((const char*)a);
 case QOS_SYS_FB_SET:if(a>=QOS_FB_W||b>=QOS_FB_H)return (unsigned)-1;
  if(takeover){uint8_t v=(uint8_t)c;fb_pkt('V',a,b,&v,1);return 0;}
  framebuffer[b*QOS_FB_W+a]=(uint8_t)c;return 0;
 case QOS_SYS_FB_COL:{ /* a = x | y0<<8, b = pointer, c = n samples down column x from y0 */
  unsigned x=a&255,y0=a>>8;
  if(x>=QOS_FB_W||y0>=QOS_FB_H||c==0||c>QOS_FB_H-y0||!readable(b,c))return (unsigned)-1;
  if(takeover){fb_pkt('V',x,y0,(const uint8_t*)b,c);return 0;}
  for(unsigned i=0;i<c;i++)framebuffer[(y0+i)*QOS_FB_W+x]=((const uint8_t*)b)[i];
  return 0;}
 case QOS_SYS_FB_CLEAR:if(takeover){hw_putc(1);hw_putc('K');hw_putc((uint8_t)a);return 0;}
  for(unsigned i=0;i<sizeof(framebuffer);i++)framebuffer[i]=(uint8_t)a;return 0;
 case QOS_SYS_STAT:{int f=file_number((const char*)a);if(f<0)return (unsigned)-1;if(f==0)return sizeof(readme)-1;if(f>=F_TMP0)return lengths[f-F_TMP0];return 0;}
 case QOS_SYS_GETPID:return current_pid;
 case QOS_SYS_YIELD:return 0; /* No hardware timer: cooperative execution only. */
 case QOS_SYS_FB_GET:if(takeover||a>=QOS_FB_W||b>=QOS_FB_H)return (unsigned)-1;return framebuffer[b*QOS_FB_W+a];
 case QOS_SYS_PS:return executions;
 case QOS_SYS_FB_ROW:{
  if(a>=QOS_FB_H || c!=QOS_FB_W || !readable(b,c))return (unsigned)-1;
  if(takeover){fb_pkt('H',0,a,(const uint8_t*)b,c);return 0;}
  for(unsigned i=0;i<QOS_FB_W;i++)framebuffer[a*QOS_FB_W+i]=((const uint8_t *)b)[i];
  return 0;
 }
 case QOS_SYS_FB_PRESENT:{
  if(takeover)return 1; /* no resident framebuffer to hash; frame data went out as packets */
  uint32_t hash=2166136261u;
  for(unsigned i=0;i<sizeof(framebuffer);i++)hash=(hash^framebuffer[i])*16777619u;
  last_present_checksum=hash;
  return hash;
 }
 case QOS_SYS_DISK_CANCEL:
  disk_active=0;return 0;
 case QOS_SYS_DISK_REQUEST:
  if(disk_active || c==0 || c>(takeover?QOS_DISK_TAKEOVER_WINDOW:QOS_DISK_WINDOW) || !writable_addr(b,c) || a>0xffffffffu-c)
   return (unsigned)-1;
  disk_dest=(uint16_t)b;disk_length=(uint16_t)c;disk_active=1;
  qos_disk_mailbox.offset=(uint32_t)a;
  qos_disk_mailbox.length=(uint32_t)c;
  qos_disk_mailbox.status=0;
  qos_disk_mailbox.request_seq=qos_disk_mailbox.request_seq+1; /* publish LAST */
  return 0;
 case QOS_SYS_DISK_POLL:
  if(!disk_active)return (unsigned)-1;
  if(qos_disk_mailbox.ready_seq!=qos_disk_mailbox.request_seq)return 0;
  if(qos_disk_mailbox.status!=1){disk_active=0;return (unsigned)-2;}
  for(unsigned i=0;i<disk_length;i++)((uint8_t*)(uintptr_t)disk_dest)[i]=qos_disk_mailbox.bytes[i];
  disk_active=0;
  return disk_length;
 case QOS_SYS_KEY_POLL:
  if(qos_input_mailbox.seq==key_seq_seen)return 0;
  key_seq_seen=qos_input_mailbox.seq;
  return qos_input_mailbox.key;

 default:return (unsigned)-1;
 }
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
void qos_takeover_run(void){
 takeover=1;current_pid=2;disk_active=0;
 qos_app_call(QOS_DOOMD_ENTRY,&api,QOS_RAM_END);
 takeover=0;disk_active=0;reboots=1;current_pid=0;
 for(uint32_t *p=__ov_start;p<__ov_end;p++)*p=0;
 qos_resume_enter(); /* switches to the (zeroed) overlay kernel stack, calls qos_resume */
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

#endif /* QOS_MODEL_BRIDGE */
