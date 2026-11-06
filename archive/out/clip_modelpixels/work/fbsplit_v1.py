"""Frame 1 view window: it is pumped in orig seg3 (step 810705), before the seg4 start state. Arm the dump there and stop
just after pump_end at a fresh pc. Writes snaps/seg9100.pkl, seg9101.pkl (+frame91.json)."""
import json, pickle, sys
from pathlib import Path
from model_doom_qwen import clone, breakpoint_at, oracle_run
from upstream_ref import symbols
import fbsplit
sy = symbols('/private/tmp/mp/bundle/build/doomd-sym.elf')
pb, pe = sy['pump_begin'], sy['pump_end']
sg = pickle.loads(open('orig/seg3.pkl', 'rb').read())
m = clone(sg['start'])
while m.steps < 810705 - 3000: m.record()
arm = clone(m); arm.ram[sy['q_dump_req'] // 4] = 1
mm = clone(arm); visited = set(); seen_b = seen_e = False
while True:
    visited.add(mm.pc)
    if mm.pc == pb: seen_b = True
    if seen_b and mm.pc == pe: seen_e = True
    mm.record()
    if seen_e and mm.pc not in visited: break
P = mm.pc; print('P', hex(P), 'steps', mm.steps - arm.steps)
breakpoint_at(arm, P)
class A: parts = 2
res = fbsplit.parts(arm, A, 9100, 'frame1-view')
Path('snaps').mkdir(exist_ok=True)
for d in res: open(f'snaps/seg{d["index"]}.pkl', 'wb').write(pickle.dumps(d, protocol=5))
Path('snaps/frame91.json').write_text(json.dumps(dict(frame=91, lens=[len(d['out']) for d in res], instr=[d['instr'] for d in res],
   tokens=[d['tokens'] for d in res], first=9100, n=len(res))))
