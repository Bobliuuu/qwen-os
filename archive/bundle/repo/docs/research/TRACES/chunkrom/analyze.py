import sys,struct,collections
import numpy as np
f=sys.argv[1]
a=np.fromfile(f,dtype='<u4').reshape(-1,4)
off,ln,ra,tic=a.T
print('reqs',len(a),'bytes',ln.sum(),'ntic max',tic.max())
# tic index = nticks at time of request (0 = before first G_Ticker)
ct=np.bincount(tic); print('req tic0',ct[0],'tic1',ct[1],'tic2..',ct[2:6],'last',len(ct))
def extents(sel):
    # merged byte intervals
    o=off[sel].astype(np.int64); e=o+ln[sel]
    idx=np.argsort(o,kind='stable'); o=o[idx]; e=e[idx]
    n=0;tot=0;cs=None;ce=None
    ext=[]
    for s,t in zip(o,e):
        if ce is None or s>ce: 
            if ce is not None: ext.append((cs,ce))
            cs,ce=s,t
        elif t>ce: ce=t
    if ce is not None: ext.append((cs,ce))
    return ext
for gap in (0,16,64):
  pass
def stats(lo,hi,gap=0):
    sel=(tic>=lo)&(tic<hi)
    ex=extents(sel)
    # merge with gap
    m=[]
    for s,e in ex:
        if m and s-m[-1][1]<=gap: m[-1][1]=max(m[-1][1],e)
        else: m.append([s,e])
    uniq=sum(e-s for s,e in ex); rom=sum(e-s for s,e in m)
    return int(sel.sum()),int(ln[sel].sum()),uniq,len(ex),len(m),rom
print('chunk  firsttic req reqbytes unique ext(exact) ext(gap16) rom(gap16)  reuse')
for lo,hi in ((0,2),(0,10),(0,20),(0,35),(0,50),(0,75),(0,100)):
    r=stats(lo,hi,16); print('prefix',lo,hi,r)
for C in (10,20,35,50,75,100):
    res=[]
    for lo in range(0,tic.max()+1,C):
        res.append(stats(lo,lo+C,16))
    ur=[x[2] for x in res]; rom=[x[5] for x in res]; ex=[x[4] for x in res]
    rq=[x[0] for x in res]; rb=[x[1] for x in res]
    print('C=%d chunks=%d  uniq max %d mean %d  rom(gap16) max %d  ext max %d mean %d  req max %d  reqbytes max %d reuse(mean) %.1f%%'%(C,len(res),max(ur),sum(ur)/len(ur),max(rom),max(ex),sum(ex)/len(ex),max(rq),max(rb),100*(1-sum(ur)/sum(rb))))
    print('   uniq per chunk',ur[:12])
