#!/usr/bin/env python3
"""Does the merged checkpoint's chip layers implement Zba (sh1add/sh2add/sh3add)?
Runs a straight-line Zba program through RvChat.generate with the lockstep oracle on (a) the HF path
(checkpoint weights, executor=False; fast=False -> every layer through HF modules) and (b) the executor path.
Every chip token the model predicts is compared with the reference machine (which implements Zba)."""
import random, sys, json
import torch
from chipformer.rv import bridge as BR, chat as C, ref
from chipformer.rv.asm import assemble

def prog(n=150, seed=1, nozba=False):
    r = random.Random(seed)
    regs = ['t0', 't1', 't2', 'a0', 'a1', 'a2', 'a3', 's2', 's3']
    L = ["_start: li a7, 93", "ecall"]
    for i, g in enumerate(regs):
        L.append(f"li {g}, {r.choice([0, 1, 7, 12345, 0x7fffffff, -5, 0x12345678, -0x7ffff000, r.getrandbits(31)])}")
    for _ in range(n):
        op = r.choice(['sh1add', 'sh2add', 'sh3add'])
        rd, a, b = r.choice(regs), r.choice(regs), r.choice(regs)
        if nozba:
            L.append(f"slli t6, {a}, {int(op[2])}")
            L.append(f"add {rd}, t6, {b}")
        else:
            L.append(f"{op} {rd}, {a}, {b}")
        if r.random() < .3:
            L.append(f"add {r.choice(regs)}, {r.choice(regs)}, {r.choice(regs)}")
    L += ["li a7, 93", "ecall"]
    return assemble("\n".join(L))

def run(path, mode, nozba=False):
    exe = {'hf': False, 'exec': True}[mode]
    chat = C.RvChat(path, fast=(mode == 'hf'), executor=exe)
    ids = chat.prompt_ids([{'role': 'user', 'content': 'Use calc to evaluate 1 + 1.'}])
    p = prog(nozba=nozba)
    m = ref.Machine.from_program(p); BR.park(m)
    m2 = ref.Machine.from_program(p); BR.park(m2)
    lock = BR.Session(chat.T, m2); lock.history(ids)
    r = chat.generate(ids, m, 4000, 4000, check_head=True, lock=lock)
    out = dict(nozba=nozba, ref_tokens_to_halt=len(lock.toks), mode=mode, chip_tokens=r['chip_tokens'], text_tokens=r['text_tokens'], lock_error=r['lock_error'], head_mismatch=r['head_mismatch'])
    print(json.dumps(out), flush=True)
    del chat; torch.cuda.empty_cache()
    return out

if __name__ == '__main__':
    nz = len(sys.argv) > 2 and sys.argv[2] == 'nozba'
    res = [run(sys.argv[1], m, nz) for m in ('exec',)]
    json.dump(res, open('/tmp/e.json', 'w'))
