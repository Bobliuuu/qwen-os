import pickle
from model_doom_qwen import clone
from upstream_ref import symbols
sy=symbols('/private/tmp/mp/bundle/build/doomd-sym.elf')
pb=sy['pump_begin']; print('pump_begin',hex(pb), 'q_frames',hex(sy['q_frames']))
for sidx in (3,4):
    sg=pickle.loads(open(f'orig/seg{sidx}.pkl','rb').read())
    m=clone(sg['start']); hits=[]
    while True:
        if m.pc==pb: hits.append(m.steps)
        m.record()
        if m.halted: break
    print('seg',sidx,'pump_begin calls',len(hits),hits[:10],'end',m.steps)
