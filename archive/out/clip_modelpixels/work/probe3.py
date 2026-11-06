import pickle,struct
from model_doom_qwen import clone
from upstream_ref import symbols
sy=symbols('/private/tmp/mp/bundle/build/doomd-sym.elf')
for sidx in (3,4):
    sg=pickle.loads(open(f'orig/seg{sidx}.pkl','rb').read())
    m=clone(sg['start']); print('seg',sidx,'q_dump_req',m.ram[sy['q_dump_req']//4],'q_frames',m.ram[sy['q_frames']//4],'steps',m.steps)
    m.ram[sy['q_dump_req']//4]=1
    last=0
    while True:
        m.record()
        if m.halted: break
        if len(m.out)!=last:
            last=len(m.out)
            if last<400 or last%5000<5: print(' steps',m.steps,'outlen',last,'frames',m.ram[sy['q_frames']//4],'dreq',m.ram[sy['q_dump_req']//4])
    print('end',m.steps,len(m.out), bytes(m.out[:60]))
