"""Frame 1: its view pump begins in orig seg3 (step 810705) and finishes in seg4, so the armed run starts at seg3 step ~807705
(rom taken from seg4's start state = seg4's stop breakpoint, without seg3's), and ends at seg4's frame-1 stop."""
import json, pickle
from pathlib import Path
from model_doom_qwen import clone
from upstream_ref import symbols
import fbsplit
sy = symbols('/private/tmp/mp/bundle/build/doomd-sym.elf')
s3 = pickle.loads(open('orig/seg3.pkl', 'rb').read()); s4 = pickle.loads(open('orig/seg4.pkl', 'rb').read())
m = clone(s3['start'])
while m.steps < 810705 - 3000: m.record()
m.rom = list(s4['start'].rom)
if hasattr(s4['start'], 'drom'): m.drom = s4['start'].drom
m.ram[sy['q_dump_req'] // 4] = 1
class A: parts = 6
res = fbsplit.parts(m, A, 100, 'frame 1 (seg3@807k..seg4 end)')
for d in res: open(f'snaps/seg{d["index"]}.pkl', 'wb').write(pickle.dumps(d, protocol=5))
Path('snaps/frame1.json').write_text(json.dumps(dict(frame=1, seg='3+4', off=0, lens=[len(d['out']) for d in res], instr=[d['instr'] for d in res],
   tokens=[d['tokens'] for d in res], first=100, n=len(res))))
