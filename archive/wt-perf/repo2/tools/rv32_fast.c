/* Fast C twin of tools/rv32_qwenputer.py + wad_device.py + key injection, for long
 * runs (DOOM). Same memory rules: fetch only 0x40000-0x7ffff, loads RAM(0..0x7fff) or
 * data ROM (0x20000-0x3ffff), stores RAM only. The "disk" device only copies requested
 * bytes into the guest mailbox; keys are written into the guest input mailbox.
 * usage: rv32_fast ELF DISK mailbox_in mailbox_disk OUT.bin max_instr [key@frame ...]
 * Frame marker: guest byte 0x02 on the console.  Keys: char@frame (e.g. w@5), 
 * a frame count of 0 means "as soon as the title/any frame exists". */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
static uint8_t mem[0x80000];
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
  if(getenv("TICLIST"))for(int i=0;i<n;i++)fprintf(stderr,"tic %d at %llu cost %llu\n",i,(unsigned long long)ticstep[i],(unsigned long long)d[i]);
  qsort(d,n,8,u64cmp);
  fprintf(stderr,"TICS n=%d first_tic_at=%llu mean=%llu median=%llu p90=%llu max=%llu\n",n,(unsigned long long)ticstep[0],(unsigned long long)(tot/n),(unsigned long long)d[n/2],(unsigned long long)d[n*9/10],(unsigned long long)mx);}
static int32_t S(uint32_t v){return (int32_t)v;}
static uint32_t rd32(uint32_t a){uint32_t v;memcpy(&v,mem+a,4);return v;}
static void wr32(uint32_t a,uint32_t v){memcpy(mem+a,&v,4);}
static void die(const char*m,uint32_t a,uint64_t steps){fprintf(stderr,"FAULT %s at %#x pc=%#x steps=%llu\n",m,a,pc,(unsigned long long)steps);for(int i=0;i<64;i++){unsigned k=(trn+i)&63;fprintf(stderr,"call %08x -> %08x sp=%08x\n",tr_pc[k],tr_to[k],tr_sp[k]);}for(int i=0;i<32;i++)fprintf(stderr,"x%d=%08x%s",i,reg[i],(i%8==7)?"\n":" ");exit(3);}
int main(int argc,char**argv){
  if(argc<7){fprintf(stderr,"usage\n");return 2;}
  FILE*f=fopen(argv[1],"rb");if(!f){perror("elf");return 2;}
  static uint8_t elf[1<<20];size_t en=fread(elf,1,sizeof elf,f);fclose(f);(void)en;
  pc=*(uint32_t*)(elf+24);uint32_t phoff=*(uint32_t*)(elf+28);uint16_t phes=*(uint16_t*)(elf+42),phn=*(uint16_t*)(elf+44);
  for(int i=0;i<phn;i++){uint32_t*p=(uint32_t*)(elf+phoff+i*phes);if(p[0]!=1)continue;memcpy(mem+p[2],elf+p[1],p[4]);}
  f=fopen(argv[2],"rb");if(!f){perror("disk");return 2;}
  fseek(f,0,SEEK_END);long dn=ftell(f);fseek(f,0,SEEK_SET);uint8_t*disk=malloc(dn);if(fread(disk,1,dn,f)!=(size_t)dn)return 2;fclose(f);
  uint32_t kbox=strtoul(argv[3],0,16),dbox=strtoul(argv[4],0,16);
  FILE*out=fopen(argv[5],"wb");uint64_t maxi=strtoull(argv[6],0,10);
  int nkeys=argc-7;struct{int c;int fr;int done;}keys[256];
  for(int i=0;i<nkeys&&i<256;i++){keys[i].c=argv[7+i][0];keys[i].fr=atoi(argv[7+i]+2);keys[i].done=0;}
  if(getenv("PROF")||getenv("REQPROF")){prof=getenv("PROF")!=0;{char*se=getenv("SYMELF");if(se){char*t=strtok(strdup(se),",");while(t){uint8_t*el2=calloc(1,1<<21);FILE*g=fopen(t,"rb");if(g){fread(el2,1,1<<21,g);fclose(g);load_syms(el2);}t=strtok(0,",");}}else load_syms(elf);}for(int i=0;i<NPH;i++)hist[i]=calloc(0x10000,4);
    char*ph=getenv("PHASES");if(ph){char*t=strtok(strdup(ph),",");while(t&&nph<NPH-1){phb[nph++]=atoi(t);t=strtok(0,",");}}}
  {const char*ts=getenv("TICSYM");if(!ts)ts="G_Ticker";const char*se=getenv("SYMELF");if(se){char*t=strtok(strdup(se),",");uint8_t*el2=calloc(1,1<<21);FILE*g=fopen(t,"rb");if(g){fread(el2,1,1<<21,g);fclose(g);
    uint32_t shoff=*(uint32_t*)(el2+32);uint16_t shes=*(uint16_t*)(el2+46),shn=*(uint16_t*)(el2+48);
    for(int i=0;i<shn;i++){const uint32_t*sh=(const uint32_t*)(el2+shoff+i*shes);if(sh[1]!=2)continue;const uint32_t*strh=(const uint32_t*)(el2+shoff+sh[6]*shes);const char*str=(const char*)el2+strh[4];
      for(uint32_t j=0;j<sh[5]/16;j++){const uint8_t*e=el2+sh[4]+j*16;if(!strcmp(str+*(uint32_t*)e,ts))ticpc=*(uint32_t*)(e+4);if(!strcmp(str+*(uint32_t*)e,"P_SetupLevel"))lvlpc=*(uint32_t*)(e+4);}}}}}
  reqprof=getenv("REQPROF")!=0;if(getenv("REQLOG"))reqlog=fopen(getenv("REQLOG"),"wb");
  uint32_t last_req=0,kseq=100;int frames=0;uint64_t steps=0,fstep[100000];int exitcode=-1;
  uint64_t last_frame_step=0;
  while(steps<maxi){
    if(pc<0x40000||pc>0x7fffc||(pc&3))die("fetch",pc,steps);
    if(pc==lvlpc&&!lvlseen){lvlseen=1;lvlstep=steps;lvlticidx=nticks;}
    if(pc==ticpc&&nticks<(1<<20)){ticreq[nticks]=nreq;ticbytes[nticks]=nbytes;ticstep[nticks++]=steps;while(phase<nph&&nticks>phb[phase])phase++;}
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
      if(reg[17]==1){int c=reg[10]&511;if(c<256){fputc(c,out);int mark=0;
  if(pskip>0){pskip--;}
  else if(ps==0){if(c==1)ps=1;else if(c==2)mark=1;}
  else if(ps==1){ps=0;if(c=='D'){ps=2;pn=0;plen=0;}else if(c=='W')pskip=10;else if(c=='P')pskip=1;else if(c=='E')pskip=2;}
  else if(ps==2){plen|=c<<(8*pn);if(++pn==2){ps=0;pskip=plen;}}
  if(mark){fstep[frames<100000?frames:99999]=steps;frames++;last_frame_step=steps;if(lvlseen&&!lvlframe)lvlframe=steps;
            for(int i=0;i<nkeys;i++)if(!keys[i].done&&frames>=keys[i].fr){keys[i].done=1;wr32(kbox+4,keys[i].c);wr32(kbox,kseq++);break;}}}}
      else if(reg[17]==93){exitcode=reg[10];goto done;}
      else die("ecall",reg[17],steps);
      break;
    default:die("opcode",w,steps);
    }
    if(rd&&op!=0x63&&op!=0x23&&op!=0x0f&&op!=0x73)reg[rd]=v;
    reg[0]=0;pc=np;steps++;
    uint32_t seq=rd32(dbox);
    if(seq&&seq!=last_req){uint32_t off=rd32(dbox+4),len=rd32(dbox+8);
      if(!len||len>256)die("bad disk request",len,steps);
      nreq++;nbytes+=len;if(reqlog){uint32_t rec[4]={off,len,reg[1],(uint32_t)nticks};fwrite(rec,4,4,reqlog);}if(reqprof){uint32_t r=reg[1];int f=0;for(int q=0;q<nrq;q++)if(rqpc[q]==r){rqn[q]++;rqb[q]+=len;f=1;break;}if(!f&&nrq<512){rqpc[nrq]=r;rqn[nrq]=1;rqb[nrq]=len;nrq++;}}last_req=seq;int good=off<=(uint32_t)dn&&len<=(uint32_t)dn-off;
      if(good)memcpy(mem+dbox+20,disk+off,len);
      wr32(dbox+16,good?1:2);wr32(dbox+12,seq);}
  }
done:
  fclose(out);if(reqlog)fclose(reqlog);if(reqprof){qsort(syms,nsyms,sizeof *syms,symcmp);for(int q=0;q<nrq;q++){uint32_t a=rqpc[q];int lo=0,hi=nsyms-1,k=-1;while(lo<=hi){int m=(lo+hi)/2;if(syms[m].a<=a){k=m;lo=m+1;}else hi=m-1;}fprintf(stderr,"REQ %8llu req %9llu B  ra=%x %s+%x\n",(unsigned long long)rqn[q],(unsigned long long)rqb[q],a,k>=0?syms[k].n:"?",k>=0?a-syms[k].a:0);}}
  if(prof)prof_report();tic_report();
  fprintf(stderr,"steps=%llu exit=%d frames=%d\n",(unsigned long long)steps,exitcode,frames);
  for(int i=0;i<frames&&i<100000;i++)fprintf(stderr,"frame %d at %llu delta %llu\n",i,(unsigned long long)fstep[i],(unsigned long long)(fstep[i]-(i?fstep[i-1]:0)));
  /* dump RAM for post-mortem */
  char rn[512];snprintf(rn,sizeof rn,"%s.ram",argv[5]);FILE*r=fopen(rn,"wb");if(r){fwrite(mem,1,0x8000,r);fclose(r);}
  return exitcode<0?1:0;
}
