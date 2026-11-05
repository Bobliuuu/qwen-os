#!/usr/bin/env python3
"""E4: per-text-token and per-segment fixed cost of the real checkpoint, executor path, on this GPU.
Runs RvChat.generate (the calc tool-call turn, ~86 text tokens + chip tokens until the lockstep stops at the first
bridge-stage divergence of this synthetic firmware; only the TIMING split is used, not its verdict) 3 times."""
import json, sys, time
import torch
from chipformer.rv import bridge as BR, chat as C, ref
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from zba_probe import prog

chat = C.RvChat(sys.argv[1], fast=False, executor=True)
ids = chat.prompt_ids([{'role': 'user', 'content': 'Use calc to evaluate 1 + 1.'}])
res = []
for it in range(3):
    p = prog(nozba=True)
    m = ref.Machine.from_program(p); BR.park(m)
    m2 = ref.Machine.from_program(p); BR.park(m2)
    lock = BR.Session(chat.T, m2); lock.history(ids)
    torch.cuda.synchronize(); t0 = time.perf_counter()
    r = chat.generate(ids, m, 4000, 4000, check_head=True, lock=lock)
    torch.cuda.synchronize(); wall = time.perf_counter() - t0
    res.append(dict(it=it, wall_s=round(wall, 3), gen_s=round(r['seconds'], 3), text_tokens=r['text_tokens'], chip_tokens=r['chip_tokens'],
                    text_s=r['text_seconds'], chip_s=r['chip_seconds'], pre_gen_fixed_s=round(wall - r['seconds'], 3),
                    ms_per_text_tok=round(1e3 * r['text_seconds'] / max(r['text_tokens'], 1), 1)))
    print(json.dumps(res[-1]), flush=True)
json.dump(res, open('/tmp/e.json', 'w'))
