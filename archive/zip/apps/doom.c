#include "qos.h"
#include "hal.h"
/* QwenOS's first WAD-driven renderer. This reads real DOOM-format MAP geometry
 * using the guest disk API; it is NOT yet the Chocolate-Doom game engine.
 * The fixed-capacity cache is intentional: 32KB of Qwenputer RAM total.
 */
#define MAX_VERT 768u
#define MAX_LINES 1024u
#define MAX_ENTRIES 8192u /* bound corrupt WAD scans; no directory RAM allocation */
#define FB_W QOS_FB_W
#define FB_H QOS_FB_H
static struct {int16_t x,y;} vertices[MAX_VERT];
static struct {uint16_t a,b;uint16_t front,back;} lines[MAX_LINES];
#define MAX_SIDES 1024u
#define MAX_SECTORS 192u
static struct {uint16_t sector;} sides[MAX_SIDES];
static struct {int16_t floor,ceiling; uint16_t light;} sectors[MAX_SECTORS];
static unsigned side_count,sector_count;
static int has_sector_data;
static unsigned vertex_count,line_count;
static int stream_mode;
static uint32_t vertex_offset,line_offset;
static uint32_t directory,count;
static uint8_t chunk[256];
static uint8_t frame[FB_W*FB_H];
static int32_t player_x,player_y;
static uint32_t rd32(const uint8_t *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static uint16_t rd16(const uint8_t *p){return (uint16_t)(p[0]|p[1]<<8);}
static int16_t signed16(const uint8_t *p){return (int16_t)rd16(p);}
#define read_disk qos_doom_wad_read
static int match8(const uint8_t *p,const char *s){
 for(unsigned i=0;i<8;i++)if(p[i]!=(uint8_t)s[i])return 0;
 return 1;
}
static int directory_entry(const qos_api *a,uint32_t i,uint8_t *d){
 if(i>=count||i>=MAX_ENTRIES||directory>0xffffffffu-i*16u-16u)return 0;
 return read_disk(a,directory+i*16u,d,16);
}
static int load_vertices(const qos_api *a,uint32_t offset,uint32_t bytes){
 if(!bytes||bytes%4u||bytes/4u>8192u)return 0;
 vertex_count=bytes/4u;
 for(unsigned i=0;i<vertex_count;i++){
  uint8_t d[4];if(!read_disk(a,offset+4*i,d,4))return 0;
  vertices[i].x=signed16(d);vertices[i].y=signed16(d+2);
 }
 return 1;
}
static int load_lines(const qos_api *a,uint32_t offset,uint32_t bytes){
 if(!bytes||bytes%14u||bytes/14u>8192u)return 0;
 line_count=bytes/14u;
 for(unsigned i=0;i<line_count;i++){
  uint8_t d[14];if(!read_disk(a,offset+14*i,d,14))return 0;
  unsigned x=rd16(d),y=rd16(d+2);
  if(x>=vertex_count||y>=vertex_count)return 0;
  lines[i].a=(uint16_t)x;lines[i].b=(uint16_t)y;
  lines[i].front=rd16(d+10);lines[i].back=rd16(d+12);
 }
 return 1;
}
static int load_sides(const qos_api *a,uint32_t offset,uint32_t bytes){
 if(!bytes||bytes%30u||bytes/30u>MAX_SIDES)return 0;
 side_count=bytes/30u;
 for(unsigned i=0;i<side_count;i++){
  uint8_t d[30];if(!read_disk(a,offset+30u*i,d,30))return 0;
  sides[i].sector=rd16(d+28);
 }
 return 1;
}
static int load_sectors(const qos_api *a,uint32_t offset,uint32_t bytes){
 if(!bytes||bytes%26u||bytes/26u>MAX_SECTORS)return 0;
 sector_count=bytes/26u;
 for(unsigned i=0;i<sector_count;i++){
  uint8_t d[26];if(!read_disk(a,offset+26u*i,d,26))return 0;
  sectors[i].floor=signed16(d);sectors[i].ceiling=signed16(d+2);
  sectors[i].light=rd16(d+20);
  if(sectors[i].ceiling<=sectors[i].floor)return 0;
 }
 return 1;
}
static int sector_at_side(unsigned si){
 if(si==0xffffu)return -1;
 if(si>=side_count||sides[si].sector>=sector_count)return -1;
 return sides[si].sector;
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
 uint32_t vo=0,vs=0,lo=0,ls=0,so=0,ss=0,co=0,cs=0;
 /* The canonical DOOM map lump order is THINGS, LINEDEFS, SIDEDEFS,
    VERTEXES, SEGS, SSECTORS, NODES, SECTORS, REJECT, BLOCKMAP. */
 for(unsigned i=(unsigned)map+1;i<count&&i<(unsigned)map+12;i++){
  if(!directory_entry(a,i,d))return 0;
  if(match8(d+8,"VERTEXES")){vo=rd32(d);vs=rd32(d+4);}
  if(match8(d+8,"LINEDEFS")){lo=rd32(d);ls=rd32(d+4);}
  if(match8(d+8,"SIDEDEFS")){so=rd32(d);ss=rd32(d+4);}
  if(match8(d+8,"SECTORS\0")){co=rd32(d);cs=rd32(d+4);}
 }
 if(!vs||!ls||vs%4u||ls%14u||vs/4u>8192u||ls/14u>8192u)return 0;
 vertex_count=vs/4u;line_count=ls/14u;
 stream_mode=(vertex_count>MAX_VERT||line_count>MAX_LINES);
 vertex_offset=vo;line_offset=lo;
 if(!stream_mode && (!load_vertices(a,vo,vs)||!load_lines(a,lo,ls)))return 0;
 has_sector_data=!stream_mode && ss && cs;
 if(has_sector_data){
  if(!load_sides(a,so,ss)||!load_sectors(a,co,cs))return 0;
  for(unsigned i=0;i<line_count;i++){
   if(sector_at_side(lines[i].front)<0)return 0;
   if(lines[i].back!=0xffffu&&sector_at_side(lines[i].back)<0)return 0;
  }
 }
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
static int get_line(const qos_api *a,unsigned i,int32_t *ax,int32_t *ay,
                    int32_t *bx,int32_t *by,unsigned *front,unsigned *back){
 if(i>=line_count)return 0;
 if(!stream_mode){
  unsigned x=lines[i].a,y=lines[i].b;
  *ax=vertices[x].x;*ay=vertices[x].y;
  *bx=vertices[y].x;*by=vertices[y].y;
  *front=lines[i].front;*back=lines[i].back;
  return 1;
 }
 uint8_t d[14],v[4];
 if(!read_disk(a,line_offset+14u*i,d,14))return 0;
 unsigned x=rd16(d),y=rd16(d+2);
 if(x>=vertex_count||y>=vertex_count)return 0;
 if(!read_disk(a,vertex_offset+4u*x,v,4))return 0;
 *ax=signed16(v);*ay=signed16(v+2);
 if(!read_disk(a,vertex_offset+4u*y,v,4))return 0;
 *bx=signed16(v);*by=signed16(v+2);
 *front=rd16(d+10);*back=rd16(d+12);
 return 1;
}
/* Cross products are exact for the 16-bit test geometry; no host math is used.
 * This is a simple segment collision check, not DOOM's blockmap slide physics. */
static int cross2(int32_t ax,int32_t ay,int32_t bx,int32_t by){
 int32_t v=ax*by-ay*bx;
 return (v>0)-(v<0);
}
static int blocked_move(const qos_api *q,int32_t nx,int32_t ny){
 for(unsigned i=0;i<line_count;i++){
  if(has_sector_data && lines[i].back!=0xffffu){
   int f=sector_at_side(lines[i].front),b=sector_at_side(lines[i].back);
   if(f>=0 && b>=0 && sectors[f].floor==sectors[b].floor &&
       sectors[f].ceiling==sectors[b].ceiling)continue;
  }
  int32_t x1,y1,x2,y2;unsigned front,back;
  if(!get_line(q,i,&x1,&y1,&x2,&y2,&front,&back))return 1;
  int32_t a=cross2(x2-x1,y2-y1,player_x-x1,player_y-y1);
  int32_t b=cross2(x2-x1,y2-y1,nx-x1,ny-y1);
  int32_t c=cross2(nx-player_x,ny-player_y,x1-player_x,y1-player_y);
  int32_t d=cross2(nx-player_x,ny-player_y,x2-player_x,y2-player_y);
  if((a==0||b==0||a!=b) && (c==0||d==0||c!=d))return 1;
 }
 return 0;
}
/* Project the real WAD LINEDEFS from the player's location. Horizontal
 * direction is one of four cardinal directions. No textures, BSP, sprites,
 * floor heights or engine game loop yet. Avoid 64-bit division helpers. */
/* One-pass geometry traversal: each streamed linedef and its vertices are
 * fetched ONCE per frame, regardless of the number of framebuffer columns.
 * This supports thousands of lines without holding the whole map in 32KB RAM.
 * This is still a flat-color ray caster, NOT DOOM's BSP renderer. */
static int draw(const qos_api *a,unsigned direction){
 int32_t nearest[FB_W],wall_height[FB_W];
 uint8_t shades[FB_W];
 for(unsigned col=0;col<FB_W;col++){
  nearest[col]=0x7fffffff;wall_height[col]=128;shades[col]=10;
 }
 for(unsigned i=0;i<line_count;i++){
  int32_t x1,y1,x2,y2;unsigned front,back;
  if(!get_line(a,i,&x1,&y1,&x2,&y2,&front,&back))return 0;
  int32_t ax=x1-player_x,ay=y1-player_y;
  int32_t sx=x2-x1,sy=y2-y1;
  int32_t effective_height=128;
  unsigned shade=10;
  if(has_sector_data){
   int f=sector_at_side(front),b=sector_at_side(back);
   if(f<0)return 0;
   if(b>=0){
    int32_t upper=sectors[f].ceiling-sectors[b].ceiling;
    int32_t lower=sectors[b].floor-sectors[f].floor;
    effective_height=upper>lower?upper:lower;
    if(effective_height<=0)continue; /* an open two-sided portal */
   }else effective_height=sectors[f].ceiling-sectors[f].floor;
   shade=10u+(sectors[f].light/32u)%8u;
  }
  for(unsigned col=0;col<FB_W;col++){
   int32_t side=((int32_t)col-(int32_t)FB_W/2)*12;
   int32_t dx=256,dy=side;
   switch(direction&3u){case 1:dx=-side;dy=256;break;
                         case 2:dx=-256;dy=-side;break;
                         case 3:dx=side;dy=-256;break;}
   int32_t den=dx*sy-dy*sx;
   if(!den)continue;
   int32_t num=ax*sy-ay*sx,edge=ax*dy-ay*dx;
   if(den<0){den=-den;num=-num;edge=-edge;}
   if(num<=0||edge>0||edge< -den)continue;
   int32_t dist=(num/den)*256+((num%den)*256)/den;
   if(dist>0 && dist<nearest[col]){
    nearest[col]=dist;wall_height[col]=effective_height;
    shades[col]=(uint8_t)(has_sector_data?shade:10u+(unsigned)(dist%8));
   }
  }
 }
 for(unsigned y=0;y<FB_H;y++)
  for(unsigned x=0;x<FB_W;x++)frame[y*FB_W+x]=(uint8_t)(y<FB_H/2?2:1);
 for(unsigned col=0;col<FB_W;col++){
  if(nearest[col]==0x7fffffff)continue;
  int32_t height=(1200/(nearest[col]+1))*wall_height[col]/128;
  if(height<1)height=1;
  if(height>FB_H)height=FB_H;
  unsigned top=(FB_H-(unsigned)height)/2;
  for(unsigned y=top;y<top+(unsigned)height;y++)frame[y*FB_W+col]=shades[col];
 }
 if(!qos_doom_present8(a,frame))return 0;
 return 1;
}
int app_main(const qos_api *a){
 if(!load_map(a)){qputs(a,"doom: no valid E1M1/MAP01 WAD map\n");return 0;}
 unsigned dir=0;
 if(!draw(a,dir)){qputs(a,"doom: geometry read error\n");return 0;}
 qputs(a,"doom: frame ready\n");
 /* A bounded interactive loop is important on a transformer CPU: each
  * frame may take tens of thousands of guest instructions. The host only
  * supplies key events and WAD pages; all rendering executes in RV32. */
 for(unsigned tick=0;tick<4;tick++){
  unsigned key=qos_doom_key(a);
  if(!key)break;
  if(key=='d')dir=(dir+1)&3u;
  else if(key=='a')dir=(dir+3)&3u;
  else if(key=='w'||key=='s'){
   int32_t delta=key=='w'?16:-16;
   int32_t dx=0,dy=0;
   switch(dir){case 0:dx=delta;break;case 1:dy=delta;break;
               case 2:dx=-delta;break;default:dy=-delta;break;}
   int32_t nx=player_x+dx,ny=player_y+dy;
   if(!blocked_move(a,nx,ny)){player_x=nx;player_y=ny;}
  }
  if(!draw(a,dir)){qputs(a,"doom: geometry read error\n");return 0;}
  qputs(a,"doom: frame ready\n");
 }
 qputs(a,"doom: WAD map geometry rendered\n");return 0;
}
