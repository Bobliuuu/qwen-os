import sys
a=open('base/v0long.h').read().split(); b=open('base/%s.h'%sys.argv[1]).read().split()
# find alignment: first new frame (b[0] or b[k]) in orig
for k in range(len(b)):
    if b[k] in a: break
j=a.index(b[k]); print('align: new[%d] == orig[%d]'%(k,j))
n=min(len(a)-j-1,len(b)-k)  # drop last orig (maybe truncated)
ok=a[j:j+n]==b[k:k+n]
print('compared %d unique frames after alignment: %s'%(n,'IDENTICAL' if ok else 'DIFFERENT'))
if not ok:
    for i in range(n):
        if a[j+i]!=b[k+i]: print('first diff at',i);break
