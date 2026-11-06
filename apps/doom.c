#include "qos.h"
#include "hal.h"
/* QwenOS /bin/doom: guest-side DOOM-format BSP renderer (NOT the full engine).
 *
 * Everything below runs as RV32IM guest instructions. The host is block
 * storage only. Per frame the guest walks the WAD's NODES front to back,
 * streaming each node (28 B), subsector (4 B), seg (12 B), vertex (4 B) and
 * linedef (14 B) record from the virtual disk. Only sidedef->sector links
 * and SECTORS heights/light are cached (RAM is ~22 KiB for this app).
 * Walls are clipped per column with DOOM-style floor/ceiling clip arrays, so
 * each pixel is written once. Missing: textures, sprites/things, monsters,
 * game logic, sound, 64-bit-safe maths for oversized maps.
 *
 * Pixel format (8-bit): bits 7..6 surface class (0 wall, 1 floor, 2 ceiling,
 * 3 sky), bits 5..0 brightness. Tools decode it to colour. */
#define SIDE_CACHE 256u
#define MAX_SECT 768u
#define MAX_VCACHE 1280u
#define MAX_ENTRIES 8192u
#define W QOS_FB_W
#define H QOS_FB_H
#define NEAR 4
#define EYE 41
#define RADIUS 16
typedef struct {int16_t fl,ce;uint8_t light,sky;} sect_t;
static uint16_t sc_tag[SIDE_CACHE],sc_val[SIDE_CACHE];
static uint32_t o_sides;
static sect_t sec[MAX_SECT];
static struct {int16_t x,y;} vcache[MAX_VCACHE];
static int vcached;

static unsigned n_sides,n_sect,n_verts,n_lines,n_nodes;
static uint32_t dir_off,lump_count;
static uint32_t o_things,o_lines,o_verts,o_segs,o_ssec,o_nodes,o_block;
static uint8_t chunk[256];
static uint8_t frame[W*H];
static int8_t ytop[W],ybot[W];
static int open_cols;
static int32_t px,py,eye,cs,sn;
static unsigned ang;
static int io_err;
static struct {uint16_t child;int16_t box[4];} stk[48];
static const int16_t sintab[65]={0,6,13,19,25,31,38,44,50,56,62,68,74,80,86,92,98,104,109,115,121,126,132,137,142,147,152,157,162,167,172,177,181,185,190,194,198,202,206,209,213,216,220,223,226,229,231,234,237,239,241,243,245,247,248,250,251,252,253,254,255,255,256,256,256};
static int32_t isin(unsigned a){
 unsigned q=(a>>6)&3,i=a&63;
 int32_t v=(q&1)?sintab[64-i]:sintab[i];
 return q&2?-v:v;
}
static uint32_t rd32(const uint8_t *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static uint16_t rd16(const uint8_t *p){return (uint16_t)(p[0]|p[1]<<8);}
static int16_t s16(const uint8_t *p){return (int16_t)rd16(p);}
static int rd(const qos_api *a,uint32_t off,void *dst,unsigned n){
 if(!qos_doom_wad_read(a,off,dst,n)){io_err=1;return 0;}
 return 1;
}
static int match8(const uint8_t *p,const char *s){
 for(unsigned i=0;i<8;i++)if(p[i]!=(uint8_t)s[i])return 0;
 return 1;
}
static int get_vertex(const qos_api *a,unsigned v,int32_t *x,int32_t *y){
 if(v>=n_verts)return 0;
 if(vcached){*x=vcache[v].x;*y=vcache[v].y;return 1;}
 uint8_t vb[4];
 if(!rd(a,o_verts+4u*v,vb,4))return 0;
 *x=s16(vb);*y=s16(vb+2);return 1;
}
/* Sector number of a sidedef (2-byte disk read, direct-mapped cache). */
static int side_sector(const qos_api *a,unsigned sd){
 if(sd>=n_sides)return -1;
 unsigned slot=sd&(SIDE_CACHE-1u);
 if(sc_tag[slot]==sd)return sc_val[slot];
 uint8_t b[2];
 if(!rd(a,o_sides+30u*sd+28u,b,2))return -1;
 unsigned v=rd16(b);
 if(v>=n_sect)return -1;
 sc_tag[slot]=(uint16_t)sd;sc_val[slot]=(uint16_t)v;
 return (int)v;
}
static int imin(int a,int b){return a<b?a:b;}
static int imax(int a,int b){return a>b?a:b;}
static int clampi(int v,int lo,int hi){return v<lo?lo:v>hi?hi:v;}
static int32_t fdiv(int32_t a,int32_t b){ /* floor division, b>0 */
 int32_t q=a/b;
 if((a%b)<0)q--;
 return q;
}
/* ---- loading ---------------------------------------------------------- */
static int load_map(const qos_api *a){
 uint8_t h[12],d[16];
 if(!rd(a,0,h,12))return 0;
 if(!(h[0]=='I'||h[0]=='P')||h[1]!='W'||h[2]!='A'||h[3]!='D')return 0;
 lump_count=rd32(h+4);dir_off=rd32(h+8);
 if(lump_count<4||lump_count>MAX_ENTRIES||dir_off>0xffffffffu-lump_count*16u)return 0;
 int map=-1;
 for(unsigned i=0;i<lump_count;i++){
  if(!rd(a,dir_off+i*16u,d,16))return 0;
  if(match8(d+8,"E1M1\0\0\0\0")||match8(d+8,"MAP01\0\0\0")){map=(int)i;break;}
 }
 if(map<0)return 0;
 uint32_t sz_t=0,sz_l=0,sz_s=0,sz_v=0,sz_g=0,sz_ss=0,sz_n=0,sz_c=0,sz_b=0;
 uint32_t o_s=0,o_c=0;
 for(unsigned i=(unsigned)map+1;i<lump_count&&i<(unsigned)map+12;i++){
  if(!rd(a,dir_off+i*16u,d,16))return 0;
  uint32_t o=rd32(d),n=rd32(d+4);
  if(match8(d+8,"THINGS\0\0")){o_things=o;sz_t=n;}
  else if(match8(d+8,"LINEDEFS")){o_lines=o;sz_l=n;}
  else if(match8(d+8,"SIDEDEFS")){o_s=o;sz_s=n;}
  else if(match8(d+8,"VERTEXES")){o_verts=o;sz_v=n;}
  else if(match8(d+8,"SEGS\0\0\0\0")){o_segs=o;sz_g=n;}
  else if(match8(d+8,"SSECTORS")){o_ssec=o;sz_ss=n;}
  else if(match8(d+8,"NODES\0\0\0")){o_nodes=o;sz_n=n;}
  else if(match8(d+8,"SECTORS\0")){o_c=o;sz_c=n;}
  else if(match8(d+8,"BLOCKMAP")){o_block=o;sz_b=n;}
 }
 if(!sz_v||!sz_l||!sz_s||!sz_c||!sz_g||!sz_ss)return 0;
 if(sz_v%4u||sz_l%14u||sz_s%30u||sz_c%26u||sz_g%12u||sz_ss%4u||sz_n%28u)return 0;
 n_verts=sz_v/4u;n_lines=sz_l/14u;n_sides=sz_s/30u;n_sect=sz_c/26u;n_nodes=sz_n/28u;
 if(n_verts>65535u||n_lines>65535u||n_sides>65534u||n_sect>MAX_SECT)return 0;
 if(!n_nodes&&sz_ss!=4u)return 0; /* no NODES: only a one-subsector map */
 if(!sz_b)o_block=0;
 (void)sz_t;
 /* VERTEXES: cached when they fit (saves ~2 disk reads per seg). */
 vcached=n_verts<=MAX_VCACHE;
 for(unsigned i=0;vcached&&i<n_verts;){
  unsigned k=n_verts-i;if(k>64)k=64;
  if(!rd(a,o_verts+4u*i,chunk,4u*k))return 0;
  for(unsigned j=0;j<k;j++,i++){vcache[i].x=s16(chunk+4*j);vcache[i].y=s16(chunk+4*j+2);}
 }
 /* SECTORS: heights, light, sky flag. */
 for(unsigned i=0;i<n_sect;){
  unsigned k=n_sect-i;if(k>9)k=9;
  if(!rd(a,o_c+26u*i,chunk,26u*k))return 0;
  for(unsigned j=0;j<k;j++,i++){
   const uint8_t *p=chunk+26*j;
   sec[i].fl=s16(p);sec[i].ce=s16(p+2);
   unsigned l=rd16(p+20);sec[i].light=(uint8_t)(l>255?255:l);
   sec[i].sky=match8(p+12,"F_SKY1\0\0");
  }
 }
 /* SIDEDEFS/LINEDEFS are NOT scanned at load (that costs ~10 guest
  * instructions per byte read); indices are validated lazily on use. */
 o_sides=o_s;
 for(unsigned i=0;i<SIDE_CACHE;i++)sc_tag[i]=0xffffu;
 /* Player 1 start. */
 px=0;py=0;ang=0;
 for(unsigned i=0;i*10u<sz_t;){
  unsigned k=sz_t/10u-i;if(k>25)k=25;
  if(!rd(a,o_things+10u*i,chunk,10u*k))return 0;
  for(unsigned j=0;j<k;j++,i++){
   const uint8_t *p=chunk+10*j;
   if(rd16(p+6)==1){px=s16(p);py=s16(p+2);ang=((unsigned)(uint16_t)s16(p+4)%360u)*256u/360u;i=sz_t;break;}
  }
 }
 return 1;
}
/* ---- BSP helpers ------------------------------------------------------ */
static int side_of(int32_t x,int32_t y,const uint8_t *n){
 int32_t nx=s16(n),ny=s16(n+2),ndx=s16(n+4),ndy=s16(n+6);
 int32_t l=ndy*(x-nx),r=(y-ny)*ndx;
 return r<l?0:1;
}
/* Sector containing (x,y): BSP descent + first seg of the subsector. */
static int locate(const qos_api *a,int32_t x,int32_t y){
 unsigned c=n_nodes?(unsigned)n_nodes-1u:0x8000u;
 uint8_t nb[28];
 for(unsigned guard=0;!(c&0x8000u)&&guard<64;guard++){
  if(c>=n_nodes||!rd(a,o_nodes+28u*c,nb,28))return -1;
  c=rd16(nb+24+2*side_of(x,y,nb));
 }
 uint8_t ss[4],sg[12],ln[14];
 if(!rd(a,o_ssec+4u*(c&0x7fffu),ss,4)||!rd(a,o_segs+12u*rd16(ss+2),sg,12))return -1;
 if(!rd(a,o_lines+14u*rd16(sg+6),ln,14))return -1;
 return side_sector(a,rd16(ln+10+2*(rd16(sg+8)&1u)));
}
/* ---- drawing ---------------------------------------------------------- */
static unsigned level(int light,int dist){
 int l=light/4-dist/20;
 return (unsigned)clampi(l,3,63);
}
static int ycoord(int32_t z,int32_t depth){return 12-((z-eye)*16)/depth;}
static void wall_span(unsigned c,int y0,int y1,int lvl){
 for(int y=y0;y<y1;y++)frame[y*W+c]=(uint8_t)(lvl);
}
static void plane_span(unsigned c,int y0,int y1,int32_t z,unsigned cls,int light){
 int32_t dz=z-eye;if(dz<0)dz=-dz;
 for(int y=y0;y<y1;y++){
  int d=2*y-23;if(d<0)d=-d;
  frame[y*W+c]=(uint8_t)(cls<<6|level(light,(dz*32)/d));
 }
}
static void column(unsigned c,int32_t depth,const sect_t *f,const sect_t *b,int contrast){
 int top=ytop[c],bot=ybot[c];
 if(top>=bot)return;
 int yc=clampi(ycoord(f->ce,depth),top,bot);
 int yf=clampi(ycoord(f->fl,depth),yc,bot);
 int light=f->light;
 if(f->sky)for(int y=top;y<yc;y++)frame[y*W+c]=(uint8_t)(3u<<6|40);
 else plane_span(c,top,yc,f->ce,2,light);
 plane_span(c,yf,bot,f->fl,1,light);
 unsigned wl=level(light+contrast,depth);
 int nt,nb;
 if(!b||b->ce<=f->fl||b->fl>=f->ce||b->ce<=b->fl){
  wall_span(c,yc,yf,(int)wl);
  nt=bot;nb=bot; /* closed */
 }else{
  nt=yc;nb=yf;
  if(b->ce<f->ce&&!(b->sky&&f->sky)){
   nt=clampi(ycoord(b->ce,depth),yc,yf);
   wall_span(c,yc,nt,(int)wl);
  }
  if(b->fl>f->fl){
   nb=clampi(ycoord(b->fl,depth),nt,yf);
   wall_span(c,nb,yf,(int)wl);
  }
 }
 ytop[c]=(int8_t)nt;ybot[c]=(int8_t)nb;
 if(nt>=nb)open_cols--;
}
/* Render one seg. Returns 0 on disk error. */
static int do_seg(const qos_api *a,const uint8_t *sg){
 unsigned v1=rd16(sg),v2=rd16(sg+2),ld=rd16(sg+6),dir=rd16(sg+8)&1u;
 uint8_t ln[14];
 int32_t x1,y1,x2,y2;
 if(ld>=n_lines||!get_vertex(a,v1,&x1,&y1)||!get_vertex(a,v2,&x2,&y2))return 0;
 /* Back-face cull in map space: front is on the right of v1->v2. */
 if((x2-x1)*(py-y1)-(y2-y1)*(px-x1)>=0)return 1;
 int32_t f1=((x1-px)*cs+(y1-py)*sn)>>8,r1=((x1-px)*sn-(y1-py)*cs)>>8;
 int32_t f2=((x2-px)*cs+(y2-py)*sn)>>8,r2=((x2-px)*sn-(y2-py)*cs)>>8;
 if(f1<NEAR&&f2<NEAR)return 1;
 if(f1<NEAR){int32_t t=(NEAR-f1);int32_t den=f2-f1;r1+=(r2-r1)*t/den;f1=NEAR;}
 else if(f2<NEAR){int32_t t=(NEAR-f2);int32_t den=f1-f2;r2+=(r1-r2)*t/den;f2=NEAR;}
 int32_t xs1=16+fdiv(16*r1,f1),xs2=16+fdiv(16*r2,f2);
 if(xs1>=xs2)return 1;
 int c0=imax(xs1,0),c1=imin(xs2,(int)W);
 if(c0>=c1)return 1;
 if(!rd(a,o_lines+14u*ld,ln,14))return 0;
 unsigned fs=rd16(ln+10+2*dir),bs=rd16(ln+12-2*dir);
 int fsec=side_sector(a,fs),bsec=bs==0xffffu?-2:side_sector(a,bs);
 if(fsec<0||bsec==-1)return 0;
 const sect_t *F=&sec[fsec],*B=bsec>=0?&sec[bsec]:0;
 int contrast=(y1==y2)?-16:(x1==x2)?16:0;
 for(int c=c0;c<c1;c++){
  if(ytop[c]>=ybot[c])continue;
  int32_t u2=2*c-31;
  int32_t den=32*(r2-r1)-u2*(f2-f1);
  int32_t depth;
  if(den<=0)depth=imin(f1,f2);
  else{
   int32_t t=((u2*f1-32*r1)*256)/den;
   t=clampi(t,0,256);
   depth=f1+(((f2-f1)*t)>>8);
  }
  if(depth<NEAR)depth=NEAR;
  column((unsigned)c,depth,F,B,contrast);
 }
 return 1;
}
static int do_subsector(const qos_api *a,unsigned ss_index){
 uint8_t ss[4];
 if(!rd(a,o_ssec+4u*ss_index,ss,4))return 0;
 unsigned count=rd16(ss),first=rd16(ss+2);
 while(count&&open_cols>0){
  unsigned k=count>20?20:count;
  if(!rd(a,o_segs+12u*first,chunk,12u*k))return 0;
  for(unsigned i=0;i<k&&open_cols>0;i++)
   if(!do_seg(a,chunk+12*i))return 0;
  first+=k;count-=k;
 }
 return 1;
}
static int box_visible(const int16_t *bx){ /* top,bottom,left,right */
 int allr=1,alll=1,allb=1,lo=W,hi=-1,anyb=0;
 for(unsigned i=0;i<4;i++){
  int32_t x=bx[2+(i&1)],y=bx[i>>1];
  int32_t dx=x-px,dy=y-py;
  int32_t f=(dx*cs+dy*sn)>>8,r=(dx*sn-dy*cs)>>8;
  if(r<=f)allr=0;
  if(r>=-f)alll=0;
  if(f>0)allb=0;
  if(f<NEAR)anyb=1;
  else{int xs=16+(int)fdiv(16*r,f);if(xs<lo)lo=xs;if(xs>hi)hi=xs;}
 }
 if(allr||alll||allb)return 0;
 if(anyb||(px>=bx[2]&&px<=bx[3]&&py>=bx[1]&&py<=bx[0])){lo=0;hi=W-1;}
 /* Occlusion: skip the box if every column it can touch is already closed. */
 lo=imax(lo,0);hi=imin(hi,(int)W-1);
 for(int c=lo;c<=hi;c++)if(ytop[c]<ybot[c])return 1;
 return 0;
}
static int draw(const qos_api *a){
 int s=locate(a,px,py);
 if(s<0)return 0;
 eye=sec[s].fl+EYE;
 cs=isin(ang+64);sn=isin(ang);
 for(unsigned i=0;i<W*H;i++)frame[i]=0;
 for(unsigned c=0;c<W;c++){ytop[c]=0;ybot[c]=H;}
 open_cols=W;
 unsigned sp=0,n=n_nodes?(unsigned)n_nodes-1u:0x8000u;
 uint8_t nb[28];
 for(;;){
  while(!(n&0x8000u)){
   if(n>=n_nodes||!rd(a,o_nodes+28u*n,nb,28))return 0;
   int near=side_of(px,py,nb);
   if(sp<48){
    stk[sp].child=rd16(nb+24+2*(near^1));
    for(unsigned i=0;i<4;i++)stk[sp].box[i]=s16(nb+8+8*(near^1)+2*i);
    sp++;
   }
   n=rd16(nb+24+2*near);
  }
  if(!do_subsector(a,n&0x7fffu))return 0;
  if(open_cols<=0)break;
  for(;;){
   if(!sp)goto done;
   sp--;
   if(box_visible(stk[sp].box)){n=stk[sp].child;break;}
  }
 }
done:
 return qos_doom_present8(a,frame);
}
/* ---- movement with BLOCKMAP collision --------------------------------- */
static int box_hits_line(int32_t x1,int32_t y1,int32_t x2,int32_t y2,int32_t bx,int32_t by){
 if(imax(x1,x2)<bx-RADIUS||imin(x1,x2)>bx+RADIUS)return 0;
 if(imax(y1,y2)<by-RADIUS||imin(y1,y2)>by+RADIUS)return 0;
 int pos=0,neg=0;
 for(unsigned i=0;i<4;i++){
  int32_t cx=bx+((i&1)?RADIUS:-RADIUS),cy=by+((i&2)?RADIUS:-RADIUS);
  int32_t v=(cx-x1)*(y2-y1)-(cy-y1)*(x2-x1);
  if(v>0)pos=1;else if(v<0)neg=1;else return 1;
 }
 return pos&&neg;
}
static int blocked(const qos_api *a,int32_t nx,int32_t ny,int32_t curfloor){
 if(!o_block)return 0;
 uint8_t hd[8];
 if(!rd(a,o_block,hd,8))return 1;
 int32_t ox=s16(hd),oy=s16(hd+2),cols=rd16(hd+4),rows=rd16(hd+6);
 int32_t bx0=(nx-RADIUS-ox)>>7,bx1=(nx+RADIUS-ox)>>7;
 int32_t by0=(ny-RADIUS-oy)>>7,by1=(ny+RADIUS-oy)>>7;
 if(bx0<0||by0<0||bx1>=cols||by1>=rows)return 1; /* off the blockmap */
 for(int32_t by=by0;by<=by1;by++)for(int32_t bx=bx0;bx<=bx1;bx++){
  uint8_t w[2];
  if(!rd(a,o_block+8u+2u*(uint32_t)(by*cols+bx),w,2))return 1;
  uint32_t lp=o_block+2u*rd16(w);
  for(unsigned guard=0;guard<256;guard++,lp+=2){
   if(!rd(a,lp,w,2))return 1;
   unsigned l=rd16(w);
   if(l==0xffffu)break;
   uint8_t ln[14];
   int32_t x1,y1,x2,y2;
   if(l>=n_lines||!rd(a,o_lines+14u*l,ln,14))return 1;
   if(!get_vertex(a,rd16(ln),&x1,&y1)||!get_vertex(a,rd16(ln+2),&x2,&y2))return 1;
   if(!box_hits_line(x1,y1,x2,y2,nx,ny))continue;
   unsigned bs=rd16(ln+12);
   if(bs==0xffffu||(rd16(ln+4)&1u))return 1; /* one-sided or impassable */
   int fsec=side_sector(a,rd16(ln+10)),bsec=side_sector(a,bs);
   if(fsec<0||bsec<0)return 1;
   const sect_t *F=&sec[fsec],*B=&sec[bsec];
   int32_t top=imin(F->ce,B->ce),bot=imax(F->fl,B->fl);
   if(top-bot<56||bot-curfloor>24||top-curfloor<56)return 1;
  }
 }
 return 0;
}
static int try_move(const qos_api *a,int32_t nx,int32_t ny){
 int s=locate(a,px,py);
 int32_t fl=s>=0?sec[s].fl:0;
 if(!blocked(a,nx,ny,fl)){px=nx;py=ny;return 1;}
 if(!blocked(a,nx,py,fl)){px=nx;return 1;}
 if(!blocked(a,px,ny,fl)){py=ny;return 1;}
 return 0;
}
int app_main(const qos_api *a){
 if(!load_map(a)){qputs(a,"doom: no valid E1M1/MAP01 WAD map\n");return 0;}
 if(!draw(a)){qputs(a,"doom: geometry read error\n");return 0;}
 qputs(a,"doom: frame ready\n");
 /* Bounded interactive loop; the host only supplies keys and WAD pages. */
 for(unsigned tick=0;tick<4;tick++){
  unsigned key=qos_doom_key(a);
  if(!key)break;
  if(key=='d')ang=(ang+256u-16u)&255u;
  else if(key=='a')ang=(ang+16u)&255u;
  else if(key=='w'||key=='s'){
   int32_t m=key=='w'?32:-32;
   int32_t c=isin(ang+64),s=isin(ang);
   try_move(a,px+((c*m)>>8),py+((s*m)>>8));
  }
  if(!draw(a)){qputs(a,"doom: geometry read error\n");return 0;}
  qputs(a,"doom: frame ready\n");
 }
 qputs(a,"doom: WAD map geometry rendered\n");return 0;
}
