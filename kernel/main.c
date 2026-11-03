#include "qos.h"
/* Qwenputer has no S-mode, MMU or kernel traps. Guest software uses a fixed
   function-pointer ABI and all guests share a single physical address space.
   Applications are separate ROM-linked ELFs, not isolated processes. */
#define FILES 8
#define FILE_SIZE 512
#define APP_STACK_BYTES 1536u
static uint8_t app_stacks[QOS_MAX_PROC][APP_STACK_BYTES] __attribute__((aligned(16)));
extern int qos_app_call(uintptr_t entry,const qos_api *api,uintptr_t stack_top);
static uint8_t framebuffer[QOS_FB_W*QOS_FB_H];
/* Firmware-visible mailbox. The model may inject external device events by
 * updating the RAM snapshot between execution bursts. Not a hardware keyboard.
 * seq is written LAST by the device driver; key code 0 means no event. */
volatile struct {uint32_t seq,key;} qos_input_mailbox;
/* Disk mailbox: an external data device may fill bytes while the model is
 * paused between execution steps. It cannot execute guest instructions.
 * ready_seq is written LAST by the driver after bytes and status are set. */
volatile struct {
 uint32_t request_seq,offset,length,ready_seq,status;
 uint8_t bytes[QOS_DISK_WINDOW];
} qos_disk_mailbox;
static uint32_t disk_active,disk_dest,disk_length,disk_seq;

static uint32_t key_seq_seen;
static uint32_t last_present_checksum;
static const char readme[]="QwenOS: RV32IM kernel, ROM apps, RAMFS, framebuffer, ABI v1.\n";
static const char * const file_names[FILES]={"/README","/bin/sh","/bin/paint","/bin/raycast","/bin/asset","/bin/doom","/tmp/note","/tmp/log"};
static char writable[2][FILE_SIZE];
static unsigned lengths[2];
typedef struct {unsigned used,owner,file,pos,write;} fd_t;
static fd_t fds[QOS_MAX_FD];
typedef struct {unsigned pid,parent,state,exitcode;} proc_t;
static proc_t procs[QOS_MAX_PROC];
static unsigned next_pid=1,current_pid=0,proc_top=0,executions=0;
static void hw_putc(uint8_t c){register unsigned a0 asm("a0")=c;register unsigned a7 asm("a7")=1;asm volatile("ecall" : "+r"(a0):"r"(a7):"memory");}
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
 else return -1;
 if(proc_top>=QOS_MAX_PROC)return -2;
 unsigned old=current_pid,slot=proc_top++,pid=next_pid++;
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
 switch(n){
 case QOS_SYS_PUTC:hw_putc((uint8_t)a);return 0;
 case QOS_SYS_OPEN: {int file=file_number((const char*)a);if(file<0)return (unsigned)-1;
  if(b==QOS_O_WRITE&&file<6)return (unsigned)-2;
  for(unsigned i=0;i<QOS_MAX_FD;i++)if(!fds[i].used){fds[i]=(fd_t){1,current_pid,(unsigned)file,0,(unsigned)b};return i;}return (unsigned)-3;}
 case QOS_SYS_READ: {unsigned fd=(unsigned)a,len=(unsigned)c;if(!getfd(fd)||!writable_addr(b,len))return (unsigned)-1;
  fd_t *f=&fds[fd];if(f->write)return (unsigned)-2;
  const char *data=0;unsigned total=0;
  if(f->file==0){data=readme;total=sizeof(readme)-1;}
  if(f->file>=6){unsigned k=f->file-6;data=writable[k];total=lengths[k];}
  if(!data)return 0;
  if(f->pos>=total)return 0;unsigned avail=total-f->pos;if(len>avail)len=avail;
  for(unsigned i=0;i<len;i++)((char*)b)[i]=data[f->pos+i];f->pos+=len;return len;}
 case QOS_SYS_CLOSE:if(!getfd((unsigned)a))return (unsigned)-1;fds[a].used=0;return 0;
 case QOS_SYS_CREATE: {int file=file_number((const char*)a);if(file<6)return (unsigned)-1;lengths[file-6]=0;return 0;}
 case QOS_SYS_WRITE:{unsigned fd=(unsigned)a,len=(unsigned)c;if(!getfd(fd)||!readable(b,len))return (unsigned)-1;
  fd_t *f=&fds[fd];if(!f->write||f->file<6)return (unsigned)-2;
  unsigned k=f->file-6;if(f->pos>FILE_SIZE)return (unsigned)-3;
  if(len>FILE_SIZE-f->pos)len=FILE_SIZE-f->pos;
  for(unsigned i=0;i<len;i++)writable[k][f->pos+i]=((const char*)b)[i];f->pos+=len;
  if(f->pos>lengths[k])lengths[k]=f->pos;return len;}
 case QOS_SYS_EXEC:if(!name_ok((const char*)a))return (unsigned)-1;return (unsigned)spawn((const char*)a);
 case QOS_SYS_FB_SET:if(a>=QOS_FB_W||b>=QOS_FB_H)return (unsigned)-1;framebuffer[b*QOS_FB_W+a]=(uint8_t)c;return 0;
 case QOS_SYS_FB_CLEAR:for(unsigned i=0;i<sizeof(framebuffer);i++)framebuffer[i]=(uint8_t)a;return 0;
 case QOS_SYS_STAT:{int f=file_number((const char*)a);if(f<0)return (unsigned)-1;if(f==0)return sizeof(readme)-1;if(f>=6)return lengths[f-6];return 0;}
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
  disk_seq++;
  qos_disk_mailbox.offset=(uint32_t)a;
  qos_disk_mailbox.length=(uint32_t)c;
  qos_disk_mailbox.status=0;
  qos_disk_mailbox.request_seq=disk_seq; /* publish LAST */
  return 0;
 case QOS_SYS_DISK_POLL:
  if(!disk_active)return (unsigned)-1;
  if(qos_disk_mailbox.ready_seq!=disk_seq)return 0;
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
int qos_main(void){
 const char *s="QwenOS: Qwenputer RV32IM kernel\n";while(*s)hw_putc(*s++);
 int rc=spawn("/bin/sh");
 if(rc||executions!=5||last_present_checksum==0)return 8;
 s="QWENOS_BOOT_OK\n";while(*s)hw_putc(*s++);
 return 0;
}
