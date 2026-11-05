/* bbtrace.h: dynamic basic-block tracer for the rv32_fast C twin (host emulator only).
 * Compiled in only with -DBBTRACE (see tools/bbtrace); without it rv32_fast is byte-for-byte the plain emulator.
 * Hooks are pure observers: they never touch guest state, so instruction count and final state must equal the
 * plain build (tests/test_bbtrace.py proves it).
 *
 * Dynamic basic block = maximal run of consecutively EXECUTED instructions that starts at the program entry or at
 * the target (taken or fall-through) of a control transfer, and ends at the first branch / jal / jalr / ecall
 * (that instruction is the last one of the block). Code is immutable (fetch only from the ROM at 0x40000+), so
 * (start pc) fixes the instruction sequence. Blocks reached at different entry points are different blocks
 * (overlap is allowed), which is the usual definition of a dynamic block.
 *
 * Output (directory $BBOUT, default "bbtrace.out"), all tab separated text:
 *   summary.txt  total instrs, blocks, truncated tail, loads/stores
 *   blocks.tsv   start len count exit_op succ_total  then up to 8 "target:count" fields + "other:count"
 *   mem.tsv      block_start slot pc is_store bytes base_reg execs same_addr_execs minaddr maxaddr  then up to 4 "stride:count" and "other:count" (stride = addr delta between consecutive execs)
 *   pairs.tsv    pc1 pc2 count      (consecutive executed instructions, across taken branches too)
 *   triples.tsv  pc1 pc2 pc3 count
 *   tics.tsv     tic start_instr instrs blocks loads stores   (tic = one entry of TICSYM, default G_Ticker; needs SYMELF)
 */
#ifndef BBTRACE_H
#define BBTRACE_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BB_NIDX 0x10000
#define BB_NSUCC 8
#define BB_MAXSLOT 64
struct bb_slot{uint32_t pc,rs1;uint8_t st,n;uint64_t ex,same;uint32_t last,minA,maxA;int have_last;int ns;int32_t sd[4];uint64_t sdc[4];uint64_t sother;};
struct bb_blk{uint32_t start,len,kindop;uint64_t cnt,other;uint32_t nsucc;uint32_t sto[BB_NSUCC];uint64_t sc[BB_NSUCC];int nslot;struct bb_slot slot[BB_MAXSLOT];};
static struct bb_blk*bb_tab[BB_NIDX];
static int bb_open;static uint32_t bb_start,bb_len,bb_nmem;
static struct{uint32_t pc,rs1;uint8_t st,n;uint32_t ad;}bb_cur[BB_MAXSLOT];
static uint64_t bb_nblocks,bb_instrs,bb_loads,bb_stores,bb_trunc;
static uint32_t bb_p1=0xffffffff,bb_p2=0xffffffff;static uint64_t bb_hist_n;
struct bb_ent{uint64_t k,c;};
#define BB_HBITS 22
static struct bb_ent*bb_pair,*bb_trip;
static uint64_t bb_npair,bb_ntrip;
static uint64_t bb_tic_blocks[1<<20],bb_tic_ld[1<<20],bb_tic_st[1<<20];

static void bb_init(void){bb_pair=calloc((size_t)1<<BB_HBITS,sizeof(struct bb_ent));bb_trip=calloc((size_t)1<<BB_HBITS,sizeof(struct bb_ent));
  if(!bb_pair||!bb_trip){fprintf(stderr,"bbtrace: oom\n");exit(2);}}
static inline void bb_bump(struct bb_ent*t,uint64_t*n,uint64_t key){
  uint64_t h=(key*0x9E3779B97F4A7C15ull)>>(64-BB_HBITS);
  for(;;){struct bb_ent*e=&t[h];if(e->c==0){e->k=key;e->c=1;if(++*n>(1ull<<BB_HBITS)*7/10){fprintf(stderr,"bbtrace: hash full\n");exit(2);}return;}
    if(e->k==key){e->c++;return;}h=(h+1)&(((uint64_t)1<<BB_HBITS)-1);}}
/* called before each instruction executes (pc already validated as a fetch address) */
static inline void bb_pre(uint32_t pc){
  if(!bb_open){bb_open=1;bb_start=pc;bb_len=0;bb_nmem=0;}}
/* pair/triple streams are fed from retired instructions only (the exit ecall is not counted in steps) */
static inline void bb_stream(uint32_t pc){
  uint32_t i=(pc-0x40000)>>2;
  if(bb_p1!=0xffffffff){uint32_t a=(bb_p1-0x40000)>>2;bb_bump(bb_pair,&bb_npair,((uint64_t)a<<16)|i);
    if(bb_p2!=0xffffffff){uint32_t b=(bb_p2-0x40000)>>2;bb_bump(bb_trip,&bb_ntrip,((uint64_t)b<<32)|((uint64_t)a<<16)|i);}}
  bb_p2=bb_p1;bb_p1=pc;}
static inline void bb_mem(uint32_t pc,int st,uint32_t ad,int n,uint32_t rs1){
  if(bb_nmem<BB_MAXSLOT){bb_cur[bb_nmem].pc=pc;bb_cur[bb_nmem].st=st;bb_cur[bb_nmem].n=n;bb_cur[bb_nmem].rs1=rs1;bb_cur[bb_nmem].ad=ad;}
  bb_nmem++;if(st)bb_stores++;else bb_loads++;}
static void bb_close(uint32_t np,uint32_t op){
  struct bb_blk*b=bb_tab[(bb_start-0x40000)>>2];
  if(!b){b=calloc(1,sizeof *b);b->start=bb_start;b->len=bb_len;b->kindop=op;bb_tab[(bb_start-0x40000)>>2]=b;}
  else if(b->len!=bb_len){fprintf(stderr,"bbtrace: block %#x length changed %u -> %u (self-modifying code?)\n",bb_start,b->len,bb_len);exit(2);}
  b->cnt++;bb_nblocks++;bb_instrs+=bb_len;
  {int k;for(k=0;k<(int)b->nsucc;k++)if(b->sto[k]==np)break;
   if(k<(int)b->nsucc)b->sc[k]++;else if(b->nsucc<BB_NSUCC){b->sto[b->nsucc]=np;b->sc[b->nsucc++]=1;}else b->other++;}
  uint32_t nm=bb_nmem<BB_MAXSLOT?bb_nmem:BB_MAXSLOT;
  if(b->nslot==0&&nm){b->nslot=nm;for(uint32_t j=0;j<nm;j++){b->slot[j].pc=bb_cur[j].pc;b->slot[j].st=bb_cur[j].st;b->slot[j].n=bb_cur[j].n;b->slot[j].rs1=bb_cur[j].rs1;b->slot[j].minA=0xffffffff;}}
  for(uint32_t j=0;j<nm&&(int)j<b->nslot;j++){struct bb_slot*s=&b->slot[j];uint32_t ad=bb_cur[j].ad;
    s->ex++;if(ad<s->minA)s->minA=ad;if(ad>s->maxA)s->maxA=ad;
    if(s->have_last){int32_t d=(int32_t)(ad-s->last);if(d==0)s->same++;
      /* exact histogram of the first 4 distinct strides (address delta between consecutive executions of this slot) */
      int k;for(k=0;k<s->ns;k++)if(s->sd[k]==d)break;
      if(k<s->ns)s->sdc[k]++;else if(s->ns<4){s->sd[s->ns]=d;s->sdc[s->ns++]=1;}else s->sother++;}
    s->last=ad;s->have_last=1;}
  bb_open=0;}
/* after the instruction retired (pc/steps updated): op = opcode, np = next pc */
static inline void bb_post(uint32_t op,uint32_t pc,uint32_t np){bb_stream(pc);bb_len++;if(op==0x63||op==0x6f||op==0x67||op==0x73)bb_close(np,op);}
static inline void bb_tic(int idx){if(idx<(1<<20)){bb_tic_blocks[idx]=bb_nblocks;bb_tic_ld[idx]=bb_loads;bb_tic_st[idx]=bb_stores;}}
static int bb_cmpk(const void*a,const void*b){const struct bb_ent*x=a,*y=b;return x->c<y->c?1:x->c>y->c?-1:0;}
static void bb_finish(uint64_t steps,const uint64_t*ticstep,int nticks){
  const char*dir=getenv("BBOUT");if(!dir)dir="bbtrace.out";char fn[1024];
  char cmd[1100];snprintf(cmd,sizeof cmd,"mkdir -p '%s'",dir);if(system(cmd)){fprintf(stderr,"bbtrace: cannot mkdir %s\n",dir);return;}
  if(bb_open&&bb_len)bb_trunc=bb_len;   /* open block at exit: counted in steps, not in any block */
  snprintf(fn,sizeof fn,"%s/summary.txt",dir);FILE*f=fopen(fn,"w");
  fprintf(f,"steps\t%llu\nblock_instrs\t%llu\ntruncated_tail_instrs\t%llu\nblock_instrs_plus_tail\t%llu\ndyn_blocks\t%llu\nloads\t%llu\nstores\t%llu\n",
    (unsigned long long)steps,(unsigned long long)bb_instrs,(unsigned long long)bb_trunc,(unsigned long long)(bb_instrs+bb_trunc),(unsigned long long)bb_nblocks,
    (unsigned long long)bb_loads,(unsigned long long)bb_stores);
  uint64_t nb=0;for(int i=0;i<BB_NIDX;i++)if(bb_tab[i])nb++;fprintf(f,"static_blocks\t%llu\nuniq_pairs\t%llu\nuniq_triples\t%llu\n",(unsigned long long)nb,(unsigned long long)bb_npair,(unsigned long long)bb_ntrip);fclose(f);
  snprintf(fn,sizeof fn,"%s/blocks.tsv",dir);f=fopen(fn,"w");FILE*m;snprintf(fn,sizeof fn,"%s/mem.tsv",dir);m=fopen(fn,"w");
  for(int i=0;i<BB_NIDX;i++){struct bb_blk*b=bb_tab[i];if(!b)continue;
    uint64_t tot=b->other;for(uint32_t k=0;k<b->nsucc;k++)tot+=b->sc[k];
    fprintf(f,"%08x\t%u\t%llu\t%02x\t%llu",b->start,b->len,(unsigned long long)b->cnt,b->kindop,(unsigned long long)tot);
    for(uint32_t k=0;k<b->nsucc;k++)fprintf(f,"\t%08x:%llu",b->sto[k],(unsigned long long)b->sc[k]);
    fprintf(f,"\tother:%llu\n",(unsigned long long)b->other);
    for(int j=0;j<b->nslot;j++){struct bb_slot*s=&b->slot[j];
      fprintf(m,"%08x\t%d\t%08x\t%d\t%d\t%u\t%llu\t%llu\t%08x\t%08x",b->start,j,s->pc,s->st,s->n,s->rs1,(unsigned long long)s->ex,(unsigned long long)s->same,s->minA,s->maxA);
      for(int k=0;k<s->ns;k++)fprintf(m,"\t%d:%llu",s->sd[k],(unsigned long long)s->sdc[k]);
      fprintf(m,"\tother:%llu\n",(unsigned long long)s->sother);}}
  fclose(f);fclose(m);
  snprintf(fn,sizeof fn,"%s/pairs.tsv",dir);f=fopen(fn,"w");qsort(bb_pair,(size_t)1<<BB_HBITS,sizeof(struct bb_ent),bb_cmpk);
  for(uint64_t i=0;i<((uint64_t)1<<BB_HBITS)&&bb_pair[i].c;i++)fprintf(f,"%08x\t%08x\t%llu\n",(unsigned)(0x40000+(((bb_pair[i].k>>16)&0xffff)<<2)),(unsigned)(0x40000+((bb_pair[i].k&0xffff)<<2)),(unsigned long long)bb_pair[i].c);fclose(f);
  snprintf(fn,sizeof fn,"%s/triples.tsv",dir);f=fopen(fn,"w");qsort(bb_trip,(size_t)1<<BB_HBITS,sizeof(struct bb_ent),bb_cmpk);
  for(uint64_t i=0;i<((uint64_t)1<<BB_HBITS)&&bb_trip[i].c;i++)fprintf(f,"%08x\t%08x\t%08x\t%llu\n",(unsigned)(0x40000+(((bb_trip[i].k>>32)&0xffff)<<2)),(unsigned)(0x40000+(((bb_trip[i].k>>16)&0xffff)<<2)),(unsigned)(0x40000+((bb_trip[i].k&0xffff)<<2)),(unsigned long long)bb_trip[i].c);fclose(f);
  snprintf(fn,sizeof fn,"%s/tics.tsv",dir);f=fopen(fn,"w");
  for(int i=0;i+1<nticks;i++)fprintf(f,"%d\t%llu\t%llu\t%llu\t%llu\t%llu\n",i,(unsigned long long)ticstep[i],(unsigned long long)(ticstep[i+1]-ticstep[i]),
    (unsigned long long)(bb_tic_blocks[i+1]-bb_tic_blocks[i]),(unsigned long long)(bb_tic_ld[i+1]-bb_tic_ld[i]),(unsigned long long)(bb_tic_st[i+1]-bb_tic_st[i]));
  fclose(f);}
#endif
