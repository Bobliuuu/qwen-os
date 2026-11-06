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
  uint32_t last_req=0,kseq=100;int frames=0;uint64_t steps=0,fstep[100000];int exitcode=-1;
  uint64_t last_frame_step=0;
  while(steps<maxi){
    if(pc<0x40000||pc>0x7fffc||(pc&3))die("fetch",pc,steps);
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
  if(mark){fstep[frames<100000?frames:99999]=steps;frames++;last_frame_step=steps;
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
      last_req=seq;int good=off<=(uint32_t)dn&&len<=(uint32_t)dn-off;
      if(good)memcpy(mem+dbox+20,disk+off,len);
      wr32(dbox+16,good?1:2);wr32(dbox+12,seq);}
  }
done:
  fclose(out);
  fprintf(stderr,"steps=%llu exit=%d frames=%d\n",(unsigned long long)steps,exitcode,frames);
  for(int i=0;i<frames&&i<100000;i++)fprintf(stderr,"frame %d at %llu delta %llu\n",i,(unsigned long long)fstep[i],(unsigned long long)(fstep[i]-(i?fstep[i-1]:0)));
  /* dump RAM for post-mortem */
  char rn[512];snprintf(rn,sizeof rn,"%s.ram",argv[5]);FILE*r=fopen(rn,"wb");if(r){fwrite(mem,1,0x8000,r);fclose(r);}
  return exitcode<0?1:0;
}
