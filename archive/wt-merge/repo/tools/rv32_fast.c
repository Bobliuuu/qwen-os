/* Fast C twin of tools/rv32_qwenputer.py + wad_device.py + key injection, for long
 * runs (DOOM).
 * Options (before the positional args):  -K schedule.txt   key-injection schedule (see tools/keysched.py)
 *   -W hexpc  key-wait park pc (default: symbol qos_key_park from SYMELF)   -F n  stop after n frame markers
 *   -v  log each injection.  Env WATCH=sym,sym (+SYMELF) prints the instruction count at the first hit of each.
 * Keyboard mailbox = 4-deep ring (include/qos.h): q[seq&3]=key then seq++ . A schedule line is
 *   shell_ready <key> | frame N <key> | <instr> <key>      (one `type` per line, in file order). Same memory rules: fetch only 0x40000-0x7ffff, loads RAM(0..0x7fff) or
 * data ROM (0x20000-0x3ffff), stores RAM only. The "disk" device only copies requested
 * bytes into the guest mailbox; keys are written into the guest input mailbox.
 * usage: rv32_fast ELF DISK mailbox_in mailbox_disk OUT.bin max_instr [key@frame ...]
 * Frame marker: guest byte 0x02 on the console.  Keys: char@frame (e.g. w@5), 
 * a frame count of 0 means "as soon as the title/any frame exists". */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <termios.h>
#include <poll.h>
#include <unistd.h>
#include <time.h>
#include <sys/ioctl.h>
static uint8_t mem[0x80000];static uint32_t syspc,sys_ra,sys_n;static uint64_t sys_st,sys_cnt[64],sys_ins[64];
#define NSR 256
static uint32_t sr_ra[NSR],sr_n[NSR];static uint64_t sr_c[NSR],sr_i[NSR];static int nsr;
static uint32_t disklat,pend_seq;static uint64_t pend_due;static FILE*fblog;static uint32_t fbaddr;
static uint32_t reg[32], pc;
static uint32_t tr_pc[64],tr_sp[64],tr_to[64];static unsigned trn;
static int ps,pskip,plen,pn;/* dump-packet parser state so pixel bytes are never taken for markers */
/* profiler: PROF=1 PHASES=f1,f2,.. (frame-marker boundaries); self-instruction count per symbol per phase */
#define NPH 8
static uint32_t *hist[NPH];static int prof,phase,nph,phb[NPH];
struct sym{uint32_t a,sz;char n[56];};static struct sym*syms;static int nsyms;
static int symcmp(const void*x,const void*y){uint32_t a=((struct sym*)x)->a,b=((struct sym*)y)->a;return a<b?-1:a>b;}
static void load_syms(const uint8_t*elf){
  uint32_t shoff=*(uint32_t*)(elf+32);uint16_t shes=*(uint16_t*)(elf+46),shn=*(uint16_t*)(elf+48);
  for(int i=0;i<shn;i++){const uint32_t*sh=(const uint32_t*)(elf+shoff+i*shes);if(sh[1]!=2)continue;
    const uint32_t*strh=(const uint32_t*)(elf+shoff+sh[6]*shes);const char*str=(const char*)elf+strh[4];
    int n=sh[5]/16;syms=realloc(syms,sizeof(struct sym)*(nsyms+n));
    for(int j=0;j<n;j++){const uint8_t*e=elf+sh[4]+j*16;uint32_t nm=*(uint32_t*)e,val=*(uint32_t*)(e+4),sz=*(uint32_t*)(e+8);uint8_t info=e[12];
      if((info&15)!=2&&(info&15)!=0)continue;if(val<0x40000||val>=0x80000)continue;if(!nm||str[nm]=='$'||(str[nm]=='.'&&str[nm+1]=='L'))continue;
      syms[nsyms].a=val;syms[nsyms].sz=sz;snprintf(syms[nsyms].n,56,"%s",str+nm);nsyms++;}
    }}
static void prof_report(void){qsort(syms,nsyms,sizeof *syms,symcmp);
  for(int ph=0;ph<=nph;ph++){uint64_t tot=0;uint64_t*acc=calloc(nsyms+1,8);
    for(uint32_t w=0;w<0x10000;w++){uint32_t c=hist[ph][w];if(!c)continue;uint32_t a=0x40000+w*4;int lo=0,hi=nsyms-1,k=nsyms;
      while(lo<=hi){int m=(lo+hi)/2;if(syms[m].a<=a){k=m;lo=m+1;}else hi=m-1;}
      acc[k]+=c;tot+=c;}
    if(getenv("PCTOP")){uint32_t*h=hist[ph];fprintf(stderr,"-- top PCs\n");for(int t=0;t<atoi(getenv("PCTOP"));t++){int b=-1;for(int w=0;w<0x10000;w++)if(h[w]&&(b<0||h[w]>h[b]))b=w;if(b<0)break;
      fprintf(stderr,"  %08x %u\n",0x40000+b*4,h[b]);h[b]=0;}}
    fprintf(stderr,"== phase %d total %llu\n",ph,(unsigned long long)tot);
    for(int t=0;t<(getenv("PTOP")?atoi(getenv("PTOP")):30);t++){int b=-1;for(int i=0;i<=nsyms;i++)if(acc[i]&&(b<0||acc[i]>acc[b]))b=i;if(b<0)break;
      unsigned long long ent=b<nsyms?hist[ph][(syms[b].a-0x40000)>>2]:0;
      fprintf(stderr,"%10llu %5.1f%% %-28s calls=%llu avg=%.1f\n",(unsigned long long)acc[b],100.0*acc[b]/tot,b<nsyms?syms[b].n:"?",ent,ent?(double)acc[b]/ent:0.0);acc[b]=0;}}}
/* tic stats: TICSYM (default G_Ticker) entry = one game tic; reports per-tic instruction deltas */
static FILE*reqlog;static int reqprof,nrq;static uint32_t rqpc[512];static uint64_t rqn[512],rqb[512];static uint64_t nreq,nbytes,ticreq[1<<20],ticbytes[1<<20];static uint32_t ticpc,lvlpc;static uint64_t lvlstep,lvlframe;static int lvlseen,lvlticidx=-1;static uint64_t ticstep[1<<20];static int nticks;
static int u64cmp(const void*a,const void*b){uint64_t x=*(uint64_t*)a,y=*(uint64_t*)b;return x<y?-1:x>y;}
static void tic_report(void){
  if(lvlseen)fprintf(stderr,"LEVEL boot_to_level_start=%llu load_to_first_frame=%llu first_game_frame_at=%llu\n",(unsigned long long)lvlstep,(unsigned long long)(lvlframe-lvlstep),(unsigned long long)lvlframe);
  if(lvlseen&&lvlticidx>=0&&nticks-lvlticidx>3){int a=lvlticidx+1;int n=nticks-1-a;static uint64_t g[1<<20];uint64_t sum=0,mx=0;
    for(int i=0;i<n;i++){g[i]=ticstep[a+i+1]-ticstep[a+i];sum+=g[i];if(g[i]>mx)mx=g[i];}
    qsort(g,n,8,u64cmp);fprintf(stderr,"GAMETICS n=%d mean=%llu median=%llu p90=%llu max=%llu total=%llu\n",n,(unsigned long long)(sum/n),(unsigned long long)g[n/2],(unsigned long long)g[n*9/10],(unsigned long long)mx,(unsigned long long)sum);
    fprintf(stderr,"DISK total_req=%llu req_per_tic=%llu bytes_per_tic=%llu\n",(unsigned long long)nreq,(unsigned long long)((ticreq[a+n]-ticreq[a])/n),(unsigned long long)((ticbytes[a+n]-ticbytes[a])/n));}
  if(nticks<2)return;static uint64_t d[1<<20];int n=nticks-1;uint64_t sum=0,mx=0;
  for(int i=0;i<n;i++){d[i]=ticstep[i+1]-ticstep[i];sum+=d[i];if(d[i]>mx)mx=d[i];}
  uint64_t tot=ticstep[n]-ticstep[0];
  if(getenv("TICLIST"))for(int i=0;i<n;i++)fprintf(stderr,"tic %d at %llu cost %llu req %llu\n",i,(unsigned long long)ticstep[i],(unsigned long long)d[i],(unsigned long long)(ticreq[i+1]-ticreq[i]));
  qsort(d,n,8,u64cmp);
  fprintf(stderr,"TICS n=%d first_tic_at=%llu mean=%llu median=%llu p90=%llu max=%llu\n",n,(unsigned long long)ticstep[0],(unsigned long long)(tot/n),(unsigned long long)d[n/2],(unsigned long long)d[n*9/10],(unsigned long long)mx);}

/* ---- live terminal mode (-L): the host is only a keyboard, a console, a block device and a display ----
 * (1) raw tty bytes -> guest keyboard mailbox ring (flow-controlled by the guest read counter, -R),
 * (2) the disk mailbox (existing), (3) guest PUTC bytes are the console; the guest's 32x24 framebuffer
 * (RAM at -B) is shown with 24-bit ANSI colours using the PLAYPAL of -A wad. No shell/game logic here.
 * Quit: Ctrl-] or Ctrl-C (never sent to the guest). Arrow keys are translated to w/s/d/a (keyboard layout). */
static uint32_t rd32(uint32_t a);static void wr32(uint32_t a,uint32_t v);static const char*live_pal_wad;static int frames_g;static int live,live_eof,live_quit,live_game,live_fps=35,live_rows=24,live_cols=80,live_term;
static uint32_t kbox_g,kseq,fbaddr,krd_addr;static uint8_t pal[256][3];
static uint8_t kq[512];static int nq,esc;static struct termios tio0;
static char clog[8][120];static int cln,clc;static uint64_t live_frames_shown,live_steps_now;
static struct timespec t_start,t_last_draw;
static double now_s(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static void live_restore(void){if(!live_term)return;live_term=0;const char*r="\x1b[0m\x1b[?25h\x1b[?1049l";if(live_game)write(1,r,strlen(r));tcsetattr(0,TCSANOW,&tio0);}
static void kpush_raw(int c){mem[kbox_g+4+(kseq&3)]=(uint8_t)c;kseq++;wr32(kbox_g,kseq);}
static void live_flush_keys(void){while(nq>0&&(int32_t)(kseq-rd32(krd_addr))<4){kpush_raw(kq[0]);memmove(kq,kq+1,--nq);}}
static void live_in(uint8_t c){
  if(esc==1){esc=(c=='[')?2:0;if(esc)return;if(c!=27){}}   /* ESC then non-'[': drop ESC, handle c */
  else if(esc==2){esc=0;int k=c=='A'?'w':c=='B'?'s':c=='C'?'d':c=='D'?'a':0;if(k&&nq<512)kq[nq++]=k;return;}
  if(c==0x1d||c==3){live_quit=1;return;}
  if(c==27){esc=1;return;}
  if(nq<512)kq[nq++]=c;}
static void live_poll(int block){struct pollfd p={0,POLLIN,0};
  if(live_eof)return;
  if(poll(&p,1,block?-1:0)>0&&(p.revents&(POLLIN|POLLHUP))){uint8_t b[64];int n=read(0,b,sizeof b);
    if(n<=0){live_eof=1;return;}for(int i=0;i<n;i++)live_in(b[i]);}
  if(esc==1&&!block){/* lone ESC (menu): deliver */ kq[nq++]=27;esc=0;}
  live_flush_keys();}
static void live_draw(int final){
  static char buf[1<<16];int n=0;
  if(!live_game){live_game=1;n+=snprintf(buf+n,sizeof buf-n,"\x1b[?1049h\x1b[2J\x1b[?25l");}
  n+=snprintf(buf+n,sizeof buf-n,"\x1b[H");
  int full=live_rows>=24+8+2;
  for(int y=0;y<(full?24:12);y++){
    for(int x=0;x<32;x++){
      if(full){const uint8_t*c=pal[mem[fbaddr+y*32+x]];n+=snprintf(buf+n,sizeof buf-n,"\x1b[48;2;%d;%d;%dm  ",c[0],c[1],c[2]);}
      else{const uint8_t*t=pal[mem[fbaddr+2*y*32+x]],*b=pal[mem[fbaddr+(2*y+1)*32+x]];
        n+=snprintf(buf+n,sizeof buf-n,"\x1b[38;2;%d;%d;%d;48;2;%d;%d;%dm\xe2\x96\x80\xe2\x96\x80",t[0],t[1],t[2],b[0],b[1],b[2]);}}
    n+=snprintf(buf+n,sizeof buf-n,"\x1b[0m\x1b[K\r\n");}
  double el=now_s()-(t_start.tv_sec+t_start.tv_nsec*1e-9);
  n+=snprintf(buf+n,sizeof buf-n,"\x1b[7m guest instr %llu | frame %d | %.1f fps | Ctrl-] quits \x1b[0m\x1b[K\r\n",(unsigned long long)live_steps_now,frames_g,el>0?live_frames_shown/el:0.0);
  int maxl=live_rows-(full?24:12)-2;if(maxl>8)maxl=8;
  for(int i=0;i<maxl;i++){int k=(cln-maxl+i);if(k<0){n+=snprintf(buf+n,sizeof buf-n,"\x1b[K\r\n");continue;}n+=snprintf(buf+n,sizeof buf-n,"%s\x1b[K\r\n",clog[k&7]);}
  (void)final;write(1,buf,n);live_frames_shown++;}
static void live_putc(int c){
  if(!live_game){char ch=(char)c;write(1,&ch,1);return;}   /* tty keeps OPOST: \n -> \r\n */
  if(c=='\n'){clog[cln&7][clc]=0;cln++;clc=0;clog[cln&7][0]=0;}else if(c>=32&&c<127&&clc<110){clog[cln&7][clc++]=(char)c;clog[cln&7][clc]=0;}}
static void live_load_pal(const char*wad){FILE*f=fopen(wad,"rb");if(!f){fprintf(stderr,"palette wad %s not found: greyscale\n",wad);for(int i=0;i<256;i++)pal[i][0]=pal[i][1]=pal[i][2]=i;return;}
  uint8_t h[12];if(fread(h,1,12,f)!=12){fclose(f);return;}uint32_t n=*(uint32_t*)(h+4),off=*(uint32_t*)(h+8);
  for(uint32_t i=0;i<n;i++){uint8_t e[16];fseek(f,off+16*i,SEEK_SET);if(fread(e,1,16,f)!=16)break;if(!memcmp(e+8,"PLAYPAL",8)){fseek(f,*(uint32_t*)e,SEEK_SET);if(fread(pal,1,768,f)!=768)break;break;}}
  fclose(f);}

static int32_t S(uint32_t v){return (int32_t)v;}
/* key-injection schedule: kind 0 = at each key-wait park (shell_ready), 1 = once N frame markers seen, 2 = once N instructions done */
static struct{int kind;uint64_t n;int key;}sched[1024];static int ns;
static int nw;static uint32_t wpc[16];static char*wn[16];static uint64_t wstep[16];static int whit[16];
static int keyparse(const char*t){
  if(!strcmp(t,"\\n")||!strcmp(t,"enter"))return '\n';if(!strcmp(t,"\\r"))return '\r';if(!strcmp(t,"\\b")||!strcmp(t,"backspace"))return 8;
  if(!strcmp(t,"\\e")||!strcmp(t,"esc"))return 27;if(!strcmp(t,"space"))return ' ';if(!strncmp(t,"0x",2))return (int)strtol(t,0,16);
  if(strlen(t)==1)return (uint8_t)t[0];fprintf(stderr,"bad key '%s'\n",t);exit(2);}
static void load_sched(const char*fn){FILE*f=fopen(fn,"r");if(!f){perror(fn);exit(2);}char ln[256];
  while(fgets(ln,sizeof ln,f)){char*h=strchr(ln,'#');if(h)*h=0;char*a=strtok(ln," \t\r\n");if(!a)continue;char*b=strtok(0," \t\r\n");char*c=strtok(0," \t\r\n");if(ns>=1024)break;
    if(!strcmp(a,"shell_ready")&&b){sched[ns].kind=0;sched[ns].key=keyparse(b);}
    else if(!strcmp(a,"frame")&&b&&c){sched[ns].kind=1;sched[ns].n=strtoull(b,0,10);sched[ns].key=keyparse(c);}
    else if(a[0]>='0'&&a[0]<='9'&&b){sched[ns].kind=2;sched[ns].n=strtoull(a,0,10);sched[ns].key=keyparse(b);}
    else{fprintf(stderr,"%s: bad schedule line near '%s'\n",fn,a);exit(2);}
    ns++;}
  fclose(f);}
static uint32_t rd32(uint32_t a){uint32_t v;memcpy(&v,mem+a,4);return v;}
static void wr32(uint32_t a,uint32_t v){memcpy(mem+a,&v,4);}
static void die(const char*m,uint32_t a,uint64_t steps){fprintf(stderr,"FAULT %s at %#x pc=%#x steps=%llu\n",m,a,pc,(unsigned long long)steps);for(int i=0;i<64;i++){unsigned k=(trn+i)&63;fprintf(stderr,"call %08x -> %08x sp=%08x\n",tr_pc[k],tr_to[k],tr_sp[k]);}for(int i=0;i<32;i++)fprintf(stderr,"x%d=%08x%s",i,reg[i],(i%8==7)?"\n":" ");exit(3);}
/* CRXPLAN=file: chunk-ROM filler (models the host rewriting the snapshot's data ROM per chunk). Records of
 * u32 start,end,nwords,words[nwords] (start/end = frame-marker counts); the words are written at CRXBASE (hex,
 * default 29000) when the marker count reaches start (record with start 0 before the first instruction). The window is zeroed
 * first. CRX chunk lines on stderr give the disk requests that happened inside each chunk (must be 0). */
static uint32_t*crxp;static size_t crxn,crxi;static uint32_t crxbase=0x29000,crxcur_lo,crxcur_hi;static uint64_t crxreq0;static int crxon;
static void crx_close(uint64_t nr){if(crxon)fprintf(stderr,"CRX chunk %u-%u reqs=%llu\n",crxcur_lo,crxcur_hi,(unsigned long long)(nr-crxreq0));crxon=0;}
static void crx_fill(unsigned nt,uint64_t nr){crx_close(nr);
  while(crxi+3<=crxn){uint32_t lo=crxp[crxi],hi=crxp[crxi+1],nw=crxp[crxi+2];if(lo>nt){break;}
    if(lo==nt){memset(mem+crxbase,0,0x3f000-crxbase);memcpy(mem+crxbase,crxp+crxi+3,nw*4);crxcur_lo=lo;crxcur_hi=hi;crxreq0=nr;crxon=1;crxi+=3+nw;break;}
    crxi+=3+nw;}}
int main(int argc,char**argv){
  const char*kfile=0;uint32_t parkpc=0;int stopframes=0,verbose=0;
  {int j=1;for(int i=1;i<argc;i++){
    if(!strcmp(argv[i],"-K")&&i+1<argc)kfile=argv[++i];
    else if(!strcmp(argv[i],"-W")&&i+1<argc)parkpc=strtoul(argv[++i],0,16);
    else if(!strcmp(argv[i],"-F")&&i+1<argc)stopframes=atoi(argv[++i]);
    else if(!strcmp(argv[i],"-v"))verbose=1;
    else if(!strcmp(argv[i],"-L"))live=1;
    else if(!strcmp(argv[i],"-B")&&i+1<argc)fbaddr=strtoul(argv[++i],0,16);
    else if(!strcmp(argv[i],"-R")&&i+1<argc)krd_addr=strtoul(argv[++i],0,16);
    else if(!strcmp(argv[i],"-A")&&i+1<argc)live_pal_wad=argv[++i];
    else if(!strcmp(argv[i],"-S")&&i+1<argc)live_fps=atoi(argv[++i]);
    else argv[j++]=argv[i];}
    argc=j;}
  if(argc<7){fprintf(stderr,"usage: rv32_fast [-K sched] [-W parkpc] [-F frames] [-v] ELF DISK kbox dbox OUT max_instr [key@frame ...]\n");return 2;}
  FILE*f=fopen(argv[1],"rb");if(!f){perror("elf");return 2;}
  static uint8_t elf[1<<20];size_t en=fread(elf,1,sizeof elf,f);fclose(f);(void)en;
  pc=*(uint32_t*)(elf+24);uint32_t phoff=*(uint32_t*)(elf+28);uint16_t phes=*(uint16_t*)(elf+42),phn=*(uint16_t*)(elf+44);
  for(int i=0;i<phn;i++){uint32_t*p=(uint32_t*)(elf+phoff+i*phes);if(p[0]!=1)continue;memcpy(mem+p[2],elf+p[1],p[4]);}
  f=fopen(argv[2],"rb");if(!f){perror("disk");return 2;}
  fseek(f,0,SEEK_END);long dn=ftell(f);fseek(f,0,SEEK_SET);uint8_t*disk=malloc(dn);if(fread(disk,1,dn,f)!=(size_t)dn)return 2;fclose(f);
  uint32_t kbox=strtoul(argv[3],0,16),dbox=strtoul(argv[4],0,16);kbox_g=kbox;
  FILE*out=fopen(argv[5],"wb");uint64_t maxi=strtoull(argv[6],0,10);
  if(live){if(!maxi)maxi=UINT64_MAX;if(!fbaddr||!krd_addr){fprintf(stderr,"live mode needs -B fbaddr -R key-read-counter-addr\n");return 2;}
    live_load_pal(live_pal_wad?live_pal_wad:"");
    if(isatty(0)){struct termios t;tcgetattr(0,&tio0);t=tio0;t.c_lflag&=~(ICANON|ECHO|ISIG);t.c_cc[VMIN]=1;t.c_cc[VTIME]=0;tcsetattr(0,TCSANOW,&t);live_term=1;
      struct winsize w;if(!ioctl(1,TIOCGWINSZ,&w)&&w.ws_row){live_rows=w.ws_row;live_cols=w.ws_col;}}
    atexit(live_restore);clock_gettime(CLOCK_MONOTONIC,&t_start);}
  for(int i=7;i<argc&&ns<1024;i++){sched[ns].kind=1;sched[ns].key=(uint8_t)argv[i][0];sched[ns].n=atoi(argv[i]+2);ns++;}
  if(kfile)load_sched(kfile);
  int si=0;uint64_t nxt=UINT64_MAX;
  #define KPUSH(why) do{mem[kbox+4+(kseq&3)]=(uint8_t)sched[si].key;kseq++;wr32(kbox,kseq);if(verbose)fprintf(stderr,"KEY step=%llu key=%d seq=%u via %s\n",(unsigned long long)steps,sched[si].key,kseq,why);si++;}while(0)
  #define NEXT_INSTR() (nxt=(si<ns&&sched[si].kind==2)?sched[si].n:UINT64_MAX)
  NEXT_INSTR();
  {const char*w=getenv("WATCH");const char*se=getenv("SYMELF");
   if(se&&(w||!parkpc)){char*t=strtok(strdup(se),",");while(t){uint8_t*el2=calloc(1,1<<21);FILE*g=fopen(t,"rb");if(g){fread(el2,1,1<<21,g);fclose(g);load_syms(el2);}t=strtok(0,",");}
     char*wl=strdup(w?w:"");for(char*t2=strtok(wl,",");t2&&nw<16;t2=strtok(0,",")){for(int q=0;q<nsyms;q++)if(!strcmp(syms[q].n,t2)){wn[nw]=strdup(t2);wpc[nw++]=syms[q].a;break;}}
     if(!parkpc)for(int q=0;q<nsyms;q++)if(!strcmp(syms[q].n,"qos_key_park"))parkpc=syms[q].a;}}
  if(getenv("PROF")||getenv("REQPROF")){prof=getenv("PROF")!=0;{char*se=getenv("SYMELF");if(se){char*t=strtok(strdup(se),",");while(t){uint8_t*el2=calloc(1,1<<21);FILE*g=fopen(t,"rb");if(g){fread(el2,1,1<<21,g);fclose(g);load_syms(el2);}t=strtok(0,",");}}else load_syms(elf);}for(int i=0;i<NPH;i++)hist[i]=calloc(0x10000,4);
    char*ph=getenv("PHASES");if(ph){char*t=strtok(strdup(ph),",");while(t&&nph<NPH-1){phb[nph++]=atoi(t);t=strtok(0,",");}}}
  {const char*ts=getenv("TICSYM");if(!ts)ts="G_Ticker";const char*se=getenv("SYMELF");if(se){char*t=strtok(strdup(se),",");uint8_t*el2=calloc(1,1<<21);FILE*g=fopen(t,"rb");if(g){fread(el2,1,1<<21,g);fclose(g);
    uint32_t shoff=*(uint32_t*)(el2+32);uint16_t shes=*(uint16_t*)(el2+46),shn=*(uint16_t*)(el2+48);
    for(int i=0;i<shn;i++){const uint32_t*sh=(const uint32_t*)(el2+shoff+i*shes);if(sh[1]!=2)continue;const uint32_t*strh=(const uint32_t*)(el2+shoff+sh[6]*shes);const char*str=(const char*)el2+strh[4];
      for(uint32_t j=0;j<sh[5]/16;j++){const uint8_t*e=el2+sh[4]+j*16;if(!strcmp(str+*(uint32_t*)e,ts))ticpc=*(uint32_t*)(e+4);if(!strcmp(str+*(uint32_t*)e,"P_SetupLevel"))lvlpc=*(uint32_t*)(e+4);}}}}}
  if(getenv("FBLOG")){fblog=fopen(getenv("FBLOG"),"w");fbaddr=strtoul(getenv("FBADDR")?getenv("FBADDR"):"170",0,16);}
  if(getenv("DISKLAT"))disklat=atoi(getenv("DISKLAT"));
  if(getenv("SYSPC"))syspc=strtoul(getenv("SYSPC"),0,16);
  reqprof=getenv("REQPROF")!=0;if(getenv("REQLOG"))reqlog=fopen(getenv("REQLOG"),"wb");
  if(getenv("CRXPLAN")){FILE*cf=fopen(getenv("CRXPLAN"),"rb");if(!cf){perror("CRXPLAN");return 2;}fseek(cf,0,SEEK_END);long cn=ftell(cf);fseek(cf,0,SEEK_SET);crxp=malloc(cn);if(fread(crxp,1,cn,cf)!=(size_t)cn)return 2;fclose(cf);crxn=cn/4;
    if(getenv("CRXBASE"))crxbase=strtoul(getenv("CRXBASE"),0,16);crx_fill(0,0);}
  uint32_t last_req=0;int frames=0;uint64_t steps=0,fstep[100000];int exitcode=-1;
  uint64_t last_frame_step=0;
  while(steps<maxi){
    if(pc<0x40000||pc>0x7fffc||(pc&3))die("fetch",pc,steps);
    if(live&&!(steps&0xFFFF)){live_steps_now=steps;live_poll(0);if(live_quit){exitcode=-3;goto done;}}
    if(steps>=nxt){while(si<ns&&sched[si].kind==2&&steps>=sched[si].n)KPUSH("instr");NEXT_INSTR();}
    if(pc==parkpc&&parkpc){ /* guest is waiting for a key (KEY_WAIT) */
      if(si<ns&&sched[si].kind!=1){if(sched[si].kind==2&&steps<sched[si].n&&verbose)fprintf(stderr,"warp: idle until instr %llu\n",(unsigned long long)sched[si].n);KPUSH(sched[si].kind?"park-warp":"shell_ready");NEXT_INSTR();}
      else if(live){live_steps_now=steps;uint32_t k0=kseq;while(kseq==k0&&!live_quit&&!live_eof)live_poll(1);
        if(live_quit){exitcode=-3;goto done;}
        if(kseq==k0){fprintf(stderr,"\r\nstdin closed while the guest waits for a key\r\n");exitcode=-2;goto done;}}
      else{fprintf(stderr,"IDLE: guest waits for a key at step %llu, nothing schedulable\n",(unsigned long long)steps);exitcode=-2;goto done;}}
    if(nw)for(int q=0;q<nw;q++)if(pc==wpc[q]&&!whit[q]){whit[q]=1;wstep[q]=steps;}
    if(pc==lvlpc&&!lvlseen){lvlseen=1;lvlstep=steps;lvlticidx=nticks;}
    if(pc==ticpc&&nticks<(1<<20)){ticreq[nticks]=nreq;ticbytes[nticks]=nbytes;ticstep[nticks++]=steps;while(phase<nph&&nticks>phb[phase])phase++;}
    if(syspc){if(pc==syspc&&!sys_ra){sys_ra=reg[1];sys_n=reg[10]&63;sys_st=steps;}
      else if(sys_ra&&pc==sys_ra){uint64_t d=steps-sys_st;sys_cnt[sys_n]++;sys_ins[sys_n]+=d;int q;for(q=0;q<nsr;q++)if(sr_ra[q]==sys_ra&&sr_n[q]==sys_n)break;
        if(q==nsr&&nsr<NSR){sr_ra[q]=sys_ra;sr_n[q]=sys_n;nsr++;}if(q<NSR){sr_c[q]++;sr_i[q]+=d;}sys_ra=0;}}
    if(prof)hist[phase][(pc-0x40000)>>2]++;
    uint32_t w=rd32(pc);
    if((w&3)!=3)die("rvc",pc,steps);
    uint32_t op=w&127,rd=(w>>7)&31,f3=(w>>12)&7,rs1=(w>>15)&31,rs2=(w>>20)&31,f7=w>>25;
    uint32_t a=reg[rs1],b=reg[rs2],v=0,np=pc+4;
    int32_t ii=S(w)>>20;int32_t is=(S(w&0xfe000000)>>20)|((w>>7)&31);
    switch(op){
    case 0x37:v=w&0xfffff000;break;
    case 0x17:v=pc+(w&0xfffff000);break;
    case 0x6f:{int32_t im=(S(w&0x80000000)>>11)|(w&0xff000)|((w>>9)&0x800)|((w>>20)&0x7fe);v=np;np=pc+im;if(rd==1){tr_pc[trn&63]=pc;tr_to[trn&63]=np;tr_sp[trn&63]=reg[2];trn++;}break;}
    case 0x67:v=np;np=(a+ii)&~1u;if(rd==1){tr_pc[trn&63]=pc;tr_to[trn&63]=np;tr_sp[trn&63]=reg[2];trn++;}break;
    case 0x63:{int32_t im=(S(w&0x80000000)>>19)|((w&0x80)<<4)|((w>>20)&0x7e0)|((w>>7)&0x1e);int c=0;
      switch(f3){case 0:c=a==b;break;case 1:c=a!=b;break;case 4:c=S(a)<S(b);break;case 5:c=S(a)>=S(b);break;case 6:c=a<b;break;case 7:c=a>=b;break;default:die("br",pc,steps);}
      if(c)np=pc+im;break;}
    case 0x03:{uint32_t ad=a+ii;int n=(f3&3)==0?1:(f3&3)==1?2:4;
      if(f3>5||f3==3)die("ld f3",pc,steps);
      if(!((ad+n<=0x8000)||(ad>=0x20000&&ad+n<=0x40000)))die("load outside data memory",ad,steps);
      if(n==1)v=mem[ad];else if(n==2){uint16_t h;memcpy(&h,mem+ad,2);v=h;}else v=rd32(ad);
      if(f3==0)v=(uint32_t)(int8_t)v;if(f3==1)v=(uint32_t)(int16_t)v;break;}
    case 0x23:{uint32_t ad=a+is;int n=f3==0?1:f3==1?2:4;if(f3>2)die("st f3",pc,steps);
      if(ad+n>0x8000)die("store outside RAM",ad,steps);
      if(n==1)mem[ad]=b;else if(n==2){uint16_t h=b;memcpy(mem+ad,&h,2);}else wr32(ad,b);break;}
    case 0x13:switch(f3){case 0:v=a+ii;break;case 2:v=S(a)<ii;break;case 3:v=a<(uint32_t)ii;break;case 4:v=a^ii;break;case 6:v=a|ii;break;case 7:v=a&ii;break;
      case 1:v=a<<((w>>20)&31);break;case 5:v=f7==0x20?(uint32_t)(S(a)>>((w>>20)&31)):a>>((w>>20)&31);break;}break;
    case 0x33:
      if(f7==1){switch(f3){
        case 0:v=a*b;break;
        case 1:v=(uint32_t)(((int64_t)S(a)*(int64_t)S(b))>>32);break;
        case 2:v=(uint32_t)(((int64_t)S(a)*(int64_t)b)>>32);break;
        case 3:v=(uint32_t)(((uint64_t)a*(uint64_t)b)>>32);break;
        case 4:v=b==0?0xffffffffu:(a==0x80000000u&&b==0xffffffffu)?0x80000000u:(uint32_t)(S(a)/S(b));break;
        case 5:v=b==0?0xffffffffu:a/b;break;
        case 6:v=b==0?a:(a==0x80000000u&&b==0xffffffffu)?0:(uint32_t)(S(a)%S(b));break;
        case 7:v=b==0?a:a%b;break;}}
      else if(f7==0||f7==0x20){uint32_t sh=b&31;switch(f3){
        case 0:v=f7?a-b:a+b;break;case 1:v=a<<sh;break;case 2:v=S(a)<S(b);break;case 3:v=a<b;break;case 4:v=a^b;break;
        case 5:v=f7?(uint32_t)(S(a)>>sh):a>>sh;break;case 6:v=a|b;break;case 7:v=a&b;break;}}
      else die("alu f7",pc,steps);
      break;
    case 0x0f:break;
    case 0x73:
      if(reg[17]==1){int c=reg[10]&511;if(c<256){fputc(c,out);int mark=0;int vis=(pskip==0&&ps==0&&c!=1&&c!=2);
  if(pskip>0){pskip--;}
  else if(ps==0){if(c==1)ps=1;else if(c==2)mark=1;}
  else if(ps==1){ps=0;if(c=='D'){ps=2;pn=0;plen=0;}else if(c=='W')pskip=10;else if(c=='P')pskip=1;else if(c=='E')pskip=2;}
  else if(ps==2){plen|=c<<(8*pn);if(++pn==2){ps=0;pskip=plen;}}
  if(live&&vis)live_putc(c);
  if(mark){if(fblog){uint32_t h=2166136261u;for(int q=0;q<768;q++)h=(h^mem[fbaddr+q])*16777619u;fprintf(fblog,"%08x\n",h);}fstep[frames<100000?frames:99999]=steps;frames++;if(crxp)crx_fill(frames,nreq);
            if(live){frames_g=frames;live_steps_now=steps;
              if(live_fps>0){double tgt=(t_start.tv_sec+t_start.tv_nsec*1e-9)+live_frames_shown/(double)live_fps,d=tgt-now_s();if(d>0)usleep((useconds_t)(d*1e6));}
              live_draw(0);live_poll(0);if(live_quit){exitcode=-3;goto done;}}last_frame_step=steps;if(lvlseen&&!lvlframe)lvlframe=steps;
            {int pushed=0;while(si<ns&&sched[si].kind==1&&frames>=(int)sched[si].n&&pushed<4){KPUSH("frame");pushed++;}NEXT_INSTR();}
            if(stopframes&&frames>=stopframes){exitcode=0;goto done;}}}}
      else if(reg[17]==93){exitcode=reg[10];goto done;}
      else die("ecall",reg[17],steps);
      break;
    default:die("opcode",w,steps);
    }
    if(rd&&op!=0x63&&op!=0x23&&op!=0x0f&&op!=0x73)reg[rd]=v;
    reg[0]=0;pc=np;steps++;
    uint32_t seq=rd32(dbox);
    if(disklat){if(seq&&seq!=last_req&&seq!=pend_seq){pend_seq=seq;pend_due=steps+disklat;}
      if(!(pend_seq&&steps>=pend_due)){goto nodisk;} seq=pend_seq;pend_seq=0;if(rd32(dbox)!=seq){goto nodisk;}}
    if(seq&&seq!=last_req){uint32_t off=rd32(dbox+4),len=rd32(dbox+8);
      if(!len||len>256)die("bad disk request",len,steps);
      nreq++;nbytes+=len;if(reqlog){uint32_t rec[5]={off,len,reg[1],(uint32_t)nticks,(uint32_t)frames};fwrite(rec,4,5,reqlog);}if(reqprof){uint32_t r=reg[1];int f=0;for(int q=0;q<nrq;q++)if(rqpc[q]==r){rqn[q]++;rqb[q]+=len;f=1;break;}if(!f&&nrq<512){rqpc[nrq]=r;rqn[nrq]=1;rqb[nrq]=len;nrq++;}}last_req=seq;int good=off<=(uint32_t)dn&&len<=(uint32_t)dn-off;
      if(good)memcpy(mem+dbox+20,disk+off,len);
      wr32(dbox+16,good?1:2);wr32(dbox+12,seq);}
    nodisk:;
  }
done:
  if(live){live_restore();
    fprintf(stderr,"\nQwenOS live: %s after %llu guest instructions, %d frames shown (%d frame markers), guest exit code %d\n",
      exitcode==-3?"quit key":exitcode==-2?"input closed":"guest exited",(unsigned long long)steps,(int)live_frames_shown,frames,exitcode);
    return exitcode==-3||exitcode==0?0:1;}
  {const char*rd=getenv("REGDUMP");if(rd){FILE*g=fopen(rd,"w");if(g){fprintf(g,"pc %08x steps %llu\n",pc,(unsigned long long)steps);for(int i=0;i<32;i++)fprintf(g,"x%d %08x\n",i,reg[i]);fclose(g);}}}
  crx_close(nreq);fclose(out);if(fblog)fclose(fblog);if(reqlog)fclose(reqlog);if(reqprof){qsort(syms,nsyms,sizeof *syms,symcmp);for(int q=0;q<nrq;q++){uint32_t a=rqpc[q];int lo=0,hi=nsyms-1,k=-1;while(lo<=hi){int m=(lo+hi)/2;if(syms[m].a<=a){k=m;lo=m+1;}else hi=m-1;}fprintf(stderr,"REQ %8llu req %9llu B  ra=%x %s+%x\n",(unsigned long long)rqn[q],(unsigned long long)rqb[q],a,k>=0?syms[k].n:"?",k>=0?a-syms[k].a:0);}}
  if(syspc){qsort(syms,nsyms,sizeof *syms,symcmp);uint64_t T=0;for(int n=0;n<64;n++)if(sys_cnt[n]){T+=sys_ins[n];fprintf(stderr,"SYS n=%2d calls=%9llu instr=%11llu avg=%.1f\n",n,(unsigned long long)sys_cnt[n],(unsigned long long)sys_ins[n],(double)sys_ins[n]/sys_cnt[n]);}
    fprintf(stderr,"SYS total instr in syscalls=%llu of %llu\n",(unsigned long long)T,(unsigned long long)steps);
    for(int q=0;q<nsr;q++){uint32_t a=sr_ra[q];int lo=0,hi=nsyms-1,k=-1;while(lo<=hi){int m=(lo+hi)/2;if(syms[m].a<=a){k=m;lo=m+1;}else hi=m-1;}fprintf(stderr,"SYSSITE n=%2u calls=%9llu instr=%11llu %s+%x\n",sr_n[q],(unsigned long long)sr_c[q],(unsigned long long)sr_i[q],k>=0?syms[k].n:"?",k>=0?a-syms[k].a:0);}}
  if(prof)prof_report();tic_report();
  for(int q=0;q<nw;q++)fprintf(stderr,"WATCH %s %s %llu\n",wn[q],whit[q]?"at":"never",(unsigned long long)wstep[q]);
  fprintf(stderr,"steps=%llu exit=%d frames=%d\n",(unsigned long long)steps,exitcode,frames);
  for(int i=0;i<frames&&i<100000;i++)fprintf(stderr,"frame %d at %llu delta %llu\n",i,(unsigned long long)fstep[i],(unsigned long long)(fstep[i]-(i?fstep[i-1]:0)));
  /* dump RAM for post-mortem */
  char rn[512];snprintf(rn,sizeof rn,"%s.ram",argv[5]);FILE*r=fopen(rn,"wb");if(r){fwrite(mem,1,0x8000,r);fclose(r);}
  return exitcode<0?1:0;
}
