#!/usr/bin/env python3
"""GPU micro-benchmark of the chip-layer executor, WITHOUT the 18.7 GB checkpoint.

STATUS: WRITTEN ON A MAC WITH NO GPU, NEVER RUN. Only `python3 -m py_compile` was checked. Treat the
first run as a debugging run; docs/research/NEURAL_EXECUTOR.md section 5 (E1) says what to expect and
what each number means. Do not launch it until the user has approved GPU spend.

It builds the RV32 circuit (core.build, no HF weights), loads a real guest window's machine snapshot,
and feeds the reference trace's own tokens (teacher forcing) through upstream's Triton Executor2 three
ways, timing each with CUDA events:

  A  graph-only: stage the embedding row, replay the CUDA graph, repeat; ONE sync at the end.
     = GPU-bound floor of one chip token (kernels + launch gaps), no Python in the loop.
  B  as RvChat.generate does it: per token embed copy, replay, read the kept dims, .tolist() (a host
     sync), decode the predicted token, compare with the reference. = what the A100 runs pay today
     minus the lockstep bookkeeping.
  C  K tokens per graph: one captured graph holding K executor bodies (inputs staged as a [K, D]
     block, outputs written to a [K, n_keep] block), one sync per K tokens. Valid for teacher-forced
     verification; shows what a device-resident decode loop could reach.

Exactness: B and C compare every predicted token with the reference token (teacher forcing: the
reference trace is the input, so a mismatch is a real circuit/executor disagreement, or a start-state
artifact if it happens at the first few positions: the real driver primes the lag taps with a text
prompt, this script does not).

  PYTHONPATH=<qwenputer>/experimental/riscv python3 tools/exec_microbench.py \
      --elf build/demo/qwenos-e1m1.elf --kernel-elf build/kernel-doomd.elf --disk E1.img \
      --tokenizer <Qwen3.5-4B tokenizer.json> --skip 0 --tokens 20000 --unroll 16
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--elf', required=True)
    ap.add_argument('--kernel-elf', required=True)
    ap.add_argument('--disk', required=True)
    ap.add_argument('--tokenizer', required=True, help='a Qwen3.5 tokenizer.json')
    ap.add_argument('--skip', type=int, default=0, help='guest instructions to run on the host first')
    ap.add_argument('--tokens', type=int, default=20000)
    ap.add_argument('--unroll', type=int, default=16)
    ap.add_argument('--profile', action='store_true', help='also print the top CUDA kernels of 200 tokens')
    ap.add_argument('--json')
    args = ap.parse_args()

    import numpy as np
    import torch
    from chipformer.q35.ir import ONE  # noqa: F401  (import check)
    from chipformer.rv import bridge as BR, core, elf as relf, ref, spec as S
    from chipformer.rv.tritonexec import Executor2
    from upstream_ref import symbols, ReferenceDiskDevice

    dev = 'cuda'
    # 1. the host reference trace (the teacher)
    sy = symbols(args.kernel_elf)
    m = ref.Machine.from_program(relf.program(args.elf))
    disk = ReferenceDiskDevice(m, sy['qos_disk_mailbox'], Path(args.disk).read_bytes())
    for _ in range(args.skip):
        m.record()
        disk.tick()
    start = ref.Machine(list(m.rom), list(m.ram), list(m.x), m.anchor, m.n, False, m.steps, m.drom,
                        [list(r) for r in m.bn])
    toks = [S.tok('GO')]
    while len(toks) < args.tokens + 1 and not m.halted:
        toks += m.record()
        disk.tick()
    toks = toks[:args.tokens + 1]
    N = len(toks) - 1
    print(f'teacher trace: {N} tokens', flush=True)

    # 2. circuit + executor (no checkpoint)
    T = BR.Text(args.tokenizer)
    t0 = time.time()
    c = core.build(core.T4B, T)
    core.snapshot(c, start)
    ex = Executor2(c, 1, dev)
    print(f'built circuit + executor in {time.time() - t0:.0f}s: {len(c.dims)} dims', flush=True)
    keep_ir = torch.tensor(c.keep, device=dev)
    ncode = core.NFAM + core.NPAY
    emb = ex.embed(toks[:N])                       # [N, D] fp32 on the GPU
    xbuf = torch.zeros(1, ex.D, device=dev)
    heads = [st for st in ex.steps if st['kind'] == 'head']

    def reset():
        for st in heads:
            st['S'].zero_()
            st['hist'].zero_()
        ex.load_init()

    def decode(codes):  # codes: [n, ncode] float tensor on cpu -> list of predicted tokens (or None)
        out = []
        for row in codes.tolist():
            if not any(row):
                out.append(None)
                continue
            bits = [1 if v > 0 else 0 for v in row]
            fid = sum(b << i for i, b in enumerate(bits[:core.NFAM]))
            p = sum(b << i for i, b in enumerate(bits[core.NFAM:]))
            out.append(core.decode_code(fid, p, T))
        return out

    def wrong(pred, lo=0):
        # a text token prediction (echo) is S.TEXT_TOKEN | qwen id in the circuit's stream
        return [lo + i for i, (p_, w_) in enumerate(zip(pred, toks[lo + 1:])) if p_ != w_]

    res = dict(tokens=N)
    torch.cuda.init()

    # ---- graph capture (single token), state saved/restored around the warm-up like ExecRow
    kbuf = torch.zeros(len(c.keep), device=dev)

    def body():
        ex.step(xbuf)
        kbuf.copy_(xbuf[0, keep_ir])

    reset()
    saved = [(st['S'].clone(), st['hist'].clone()) for st in heads]
    s = torch.cuda.Stream()
    s.wait_stream(torch.cuda.current_stream())
    with torch.cuda.stream(s):
        for _ in range(3):
            body()
    torch.cuda.current_stream().wait_stream(s)
    g1 = torch.cuda.CUDAGraph()
    with torch.cuda.graph(g1):
        body()
    for st, (S_, h) in zip(heads, saved):
        st['S'].copy_(S_)
        st['hist'].copy_(h)

    # ---- B: the host loop of RvChat.generate
    reset()
    torch.cuda.synchronize()
    pred = []
    t0 = time.time()
    for t in range(N):
        xbuf.copy_(emb[t:t + 1])
        g1.replay()
        pred.append(kbuf[:ncode].tolist())  # .tolist() = host sync
    torch.cuda.synchronize()
    tb = time.time() - t0
    codes = torch.tensor(pred)
    bad = wrong(decode(codes))
    res['B_host_loop'] = dict(seconds=round(tb, 3), tok_per_s=round(N / tb, 1), us_per_tok=round(1e6 * tb / N, 1),
                              mismatches=len(bad), first_mismatches=bad[:10])
    print('B', res['B_host_loop'], flush=True)

    # ---- A: graph-only, no host sync inside the loop
    reset()
    torch.cuda.synchronize()
    e0, e1 = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    e0.record()
    for t in range(N):
        xbuf.copy_(emb[t:t + 1])
        g1.replay()
    e1.record()
    torch.cuda.synchronize()
    ta = e0.elapsed_time(e1) / 1e3
    res['A_graph_only'] = dict(seconds=round(ta, 3), tok_per_s=round(N / ta, 1), us_per_tok=round(1e6 * ta / N, 1))
    print('A', res['A_graph_only'], flush=True)

    # ---- C: K executor bodies in one graph
    K = args.unroll
    stage = torch.zeros(K, ex.D, device=dev)
    kout = torch.zeros(K, len(c.keep), device=dev)

    def bodyK():
        for k in range(K):
            xbuf.copy_(stage[k:k + 1])
            ex.step(xbuf)
            kout[k].copy_(xbuf[0, keep_ir])

    reset()
    saved = [(st['S'].clone(), st['hist'].clone()) for st in heads]
    s = torch.cuda.Stream()
    s.wait_stream(torch.cuda.current_stream())
    with torch.cuda.stream(s):
        for _ in range(2):
            bodyK()
    torch.cuda.current_stream().wait_stream(s)
    gK = torch.cuda.CUDAGraph()
    with torch.cuda.graph(gK):
        bodyK()
    for st, (S_, h) in zip(heads, saved):
        st['S'].copy_(S_)
        st['hist'].copy_(h)
    reset()
    torch.cuda.synchronize()
    groups = N // K
    outs = []
    t0 = time.time()
    for gi in range(groups):
        stage.copy_(emb[gi * K:(gi + 1) * K])
        gK.replay()
        outs.append(kout[:, :ncode].clone())
    torch.cuda.synchronize()
    tc = time.time() - t0
    predC = decode(torch.cat(outs).cpu())
    badC = wrong(predC)
    n = groups * K
    res['C_unrolled'] = dict(K=K, tokens=n, seconds=round(tc, 3), tok_per_s=round(n / tc, 1),
                             us_per_tok=round(1e6 * tc / n, 1), mismatches=len(badC), first_mismatches=badC[:10])
    print('C', res['C_unrolled'], flush=True)

    if args.profile:
        from torch.profiler import profile, ProfilerActivity
        reset()
        with profile(activities=[ProfilerActivity.CUDA, ProfilerActivity.CPU]) as prof:
            for t in range(200):
                xbuf.copy_(emb[t:t + 1])
                g1.replay()
            torch.cuda.synchronize()
        print(prof.key_averages().table(sort_by='cuda_time_total', row_limit=15))

    res['gpu'] = torch.cuda.get_device_name(0)
    out = json.dumps(res, indent=1)
    print(out)
    if args.json:
        Path(args.json).write_text(out)


if __name__ == '__main__':
    main()
