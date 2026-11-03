#include "qos.h"
/* QwenOS's first WAD-driven renderer. This reads real DOOM-format MAP geometry
 * using the guest disk API; it is NOT yet the Chocolate-Doom game engine.
 * The fixed-capacity cache is intentional: 32KB of Qwenputer RAM total.
 */
#define MAX_VERT 64u
#define MAX_LINES 96u
#define MAX_ENTRIES 256u
#define FB_W QOS_FB_W
#define FB_H QOS_FB_H
static struct {int16_t x,y;} vertices[MAX_VERT];
static struct {uint16_t a,b;} lines[MAX_LINES];
static unsigned vertex_count,line_count;
static uint32_t directory,count;
static uint8_t chunk[256];
static uint8_t row[FB_W];
static int32_t player_x,player_y;
static uint32_t rd32(const uint8_t *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static uint16_t rd16(const uint8_t *p){return (uint16_t)(p[0]|p[1]<<8);}
static int16_t signed16(const uint8_t *p){return (int16_t)rd16(p);}
static int read_disk(const qos_api *a,uint32_t off,uint8_t *dst,unsigned n){
 while(n){
  unsigned count=n>256u?256u:n;
  if(qcall(a,QOS_SYS_DISK_REQUEST,off,(uintptr_t)dst,count))return 0;
  unsigned ok=0;
  for(unsigned j=0;j<16;j++){
   uint32_t r=qcall(a,QOS_SYS_DISK_POLL,0,0,0);
   if(r==count){ok=1;break;}
   if(r)return 0;
  }
  if(!ok){qcall(a,QOS_SYS_DISK_CANCEL,0,0,0);return 0;}
  off+=count;dst+=count;n-=count;
 }
 return 1;
}
static int match8(const uint8_t *p,const char *s){
 for(unsigned i=0;i<8;i++)if(p[i]!=(uint8_t)s[i])return 0;
 return 1;
}
static int directory_entry(const qos_api *a,uint32_t i,uint8_t *d){
 if(i>=count||i>MAX_ENTRIES||directory>0xffffffffu-i*16u-16u)return 0;
 return read_disk(a,directory+i*16u,d,16);
}
static int load_vertices(const qos_api *a,uint32_t offset,uint32_t bytes){
 if(!bytes||bytes%4u||bytes/4u>MAX_VERT)return 0;
 vertex_count=bytes/4u;
 for(unsigned i=0;i<vertex_count;i++){
  uint8_t d[4];if(!read_disk(a,offset+4*i,d,4))return 0;
  vertices[i].x=signed16(d);vertices[i].y=signed16(d+2);
 }
 return 1;
}
static int load_lines(const qos_api *a,uint32_t offset,uint32_t bytes){
 if(!bytes||bytes%14u||bytes/14u>MAX_LINES)return 0;
 line_count=bytes/14u;
 for(unsigned i=0;i<line_count;i++){
  uint8_t d[14];if(!read_disk(a,offset+14*i,d,14))return 0;
  unsigned x=rd16(d),y=rd16(d+2);
  if(x>=vertex_count||y>=vertex_count)return 0;
  lines[i].a=(uint16_t)x;lines[i].b=(uint16_t)y;
 }
 return 1;
}
static int load_map(const qos_api *a){
 uint8_t header[12];if(!read_disk(a,0,header,12))return 0;
 if(!(header[0]=='I'||header[0]=='P')||header[1]!='W'||header[2]!='A'||header[3]!='D')return 0;
 count=rd32(header+4);directory=rd32(header+8);
 if(count<4||count>MAX_ENTRIES||directory>0xffffffffu-count*16u)return 0;
 int map=-1;uint8_t d[16];
 for(unsigned i=0;i<count;i++){
  if(!directory_entry(a,i,d))return 0;
  if(match8(d+8,"E1M1\0\0\0\0")||match8(d+8,"MAP01\0\0\0")){map=(int)i;break;}
 }
 if(map<0)return 0;
 uint32_t vo=0,vs=0,lo=0,ls=0;
 /* The canonical DOOM map lump order is THINGS, LINEDEFS, SIDEDEFS,
    VERTEXES, SEGS, SSECTORS, NODES, SECTORS, REJECT, BLOCKMAP. */
 for(unsigned i=(unsigned)map+1;i<count&&i<(unsigned)map+12;i++){
  if(!directory_entry(a,i,d))return 0;
  if(match8(d+8,"VERTEXES")){vo=rd32(d);vs=rd32(d+4);}
  if(match8(d+8,"LINEDEFS")){lo=rd32(d);ls=rd32(d+4);}
 }
 if(!vs||!ls||!load_vertices(a,vo,vs)||!load_lines(a,lo,ls))return 0;
 player_x=0;player_y=0;
 /* Pick a THINGS player-1 start when available. */
 if(directory_entry(a,(unsigned)map+1,d)&&match8(d+8,"THINGS\0\0")){
  uint32_t off=rd32(d),bytes=rd32(d+4);
  for(unsigned i=0;i<bytes/10&&i<32;i++){
   uint8_t thing[10];if(!read_disk(a,off+i*10,thing,10))return 0;
   if(rd16(thing+6)==1){player_x=signed16(thing);player_y=signed16(thing+2);break;}
  }
 }
 return 1;
}
/* Project the real WAD LINEDEFS from the player's location. Horizontal
 * direction is one of four cardinal directions. No textures, BSP, sprites,
 * floor heights or engine game loop yet. Avoid 64-bit division helpers. */
static void draw(const qos_api *a,unsigned direction){
 for(unsigned y=0;y<FB_H;y++){
  for(unsigned x=0;x<FB_W;x++)row[x]=(uint8_t)(y<FB_H/2?2:1);
  qcall(a,QOS_SYS_FB_ROW,y,(uintptr_t)row,FB_W);
 }
 for(unsigned col=0;col<FB_W;col++){
  int32_t side=((int32_t)col-(int32_t)FB_W/2)*12;
  int32_t dx=256,dy=side;
  switch(direction&3u){case 1:dx=-side;dy=256;break;case 2:dx=-256;dy=-side;break;case 3:dx=side;dy=-256;break;}
  int32_t closest=0x7fffffff;
  for(unsigned i=0;i<line_count;i++){
   int32_t ax=vertices[lines[i].a].x-player_x,ay=vertices[lines[i].a].y-player_y;
   int32_t sx=vertices[lines[i].b].x-vertices[lines[i].a].x;
   int32_t sy=vertices[lines[i].b].y-vertices[lines[i].a].y;
   int32_t den=dx*sy-dy*sx;
   if(!den)continue;
   int32_t num=ax*sy-ay*sx,edge=ax*dy-ay*dx;
   if(den<0){den=-den;num=-num;edge=-edge;}
   if(num<=0||edge>0||edge< -den)continue;
   /* num / den is ray distance in 1/256 map units; range reduced
    * before multiplying to avoid signed overflow for ordinary maps. */
   int32_t dist=(num/den)*256+((num%den)*256)/den;
   if(dist>0&&dist<closest)closest=dist;
  }
  if(closest==0x7fffffff)continue;
  int32_t height=1200/(closest+1);
  if(height>FB_H)height=FB_H;
  if(height<1)height=1;
  unsigned top=(FB_H-(unsigned)height)/2;
  for(unsigned y=top;y<top+(unsigned)height;y++)qcall(a,QOS_SYS_FB_SET,col,y,10u+(unsigned)(closest%8));
 }
 qcall(a,QOS_SYS_FB_PRESENT,0,0,0);
}
int app_main(const qos_api *a){
 if(!load_map(a)){qputs(a,"doom: no valid E1M1/MAP01 WAD map\n");return 0;}
 unsigned key=qcall(a,QOS_SYS_KEY_POLL,0,0,0);
 unsigned dir=0;
 if(key=='d')dir=1;else if(key=='s')dir=2;else if(key=='a')dir=3;
 draw(a,dir);
 qputs(a,"doom: WAD map geometry rendered\n");return 0;
}
