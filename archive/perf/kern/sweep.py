#!/usr/bin/env python3
"""Same-process A/B of executor variants: bit-exact kout/residual/state comparison + graph-only timing."""
import argparse, importlib, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--elf'); ap.add_argument('--kernel-elf'); ap.add_argument('--disk'); ap.add_argument('--tokenizer')
    ap.add_argument('--skip', type=int, default=0); ap.add_argument('--tokens', type=int, default=20000)
    ap.add_argument('--cfgs', required=True, help='json list of [name, module, {attr:val}]')
    ap.add_argument('--json')
    args = ap.parse_args()
    import torch
    from chipformer.rv import bridge as BR, core, elf as relf, ref, spec as S
    from upstream_ref import symbols, ReferenceDiskDevice
    dev = 'cuda'
    sy = symbols(args.kernel_elf)
    m = ref.Machine.from_program(relf.program(args.elf))
    disk = ReferenceDiskDevice(m, sy['qos_disk_mailbox'], Path(args.disk).read_bytes())
    for _ in range(args.skip):
        m.record(); disk.tick()
    start = ref.Machine(list(m.rom), list(m.ram), list(m.x), m.anchor, m.n, False, m.steps, m.drom, [list(r) for r in m.bn])
    toks = [S.tok('GO')]
    while len(toks) < args.tokens + 1 and not m.halted:
        toks += m.record(); disk.tick()
    toks = toks[:args.tokens + 1]; N = len(toks) - 1
    print('teacher trace', N, flush=True)
    T = BR.Text(args.tokenizer)
    c = core.build(core.T4B, T)
    core.snapshot(c, start)
    keep_ir = torch.tensor(c.keep, device=dev)
    cfgs = json.loads(args.cfgs)
    ref_res = None
    results = []
    for name, modname, attrs in cfgs:
        mod = importlib.import_module(modname)
        ex = mod.Executor2(c, 1, dev)
        for k, v in attrs.items():
            setattr(ex, k, v)
        emb = ex.embed(toks[:N])
        xbuf = torch.zeros(1, ex.D, device=dev)
        kbuf = torch.zeros(len(c.keep), device=dev)
        heads = [st for st in ex.steps if st['kind'] == 'head']
        def reset():
            for st in heads:
                st['S'].zero_(); st['hist'].zero_()
            ex.load_init()
            ex.y.zero_()
            if hasattr(ex, 'post_reset'):
                ex.post_reset()
        def body():
            ex.step(xbuf); kbuf.copy_(xbuf[0, keep_ir])
        reset()
        s = torch.cuda.Stream(); s.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(s):
            for _ in range(3):
                body()
        torch.cuda.current_stream().wait_stream(s)
        g = torch.cuda.CUDAGraph()
        with torch.cuda.graph(g):
            body()
        # check pass
        reset(); torch.cuda.synchronize()
        out = torch.zeros(N, len(c.keep), device=dev); xs = []
        for t in range(N):
            xbuf.copy_(emb[t:t + 1]); g.replay(); out[t].copy_(kbuf)
            if t % 97 == 0:
                xs.append(xbuf.clone())
        torch.cuda.synchronize()
        xs = torch.cat(xs)
        state = torch.cat([st['S'].flatten() for st in heads] + [st['hist'].flatten() for st in heads])
        # timing pass
        best = 1e9
        for _ in range(3):
            reset(); torch.cuda.synchronize()
            e0, e1 = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            e0.record()
            for t in range(N):
                xbuf.copy_(emb[t:t + 1]); g.replay()
            e1.record(); torch.cuda.synchronize()
            best = min(best, e0.elapsed_time(e1) * 1e3 / N)
        r = dict(name=name, us_per_tok=round(best, 1))
        if name.startswith('P_'):
            from torch.profiler import profile, ProfilerActivity
            reset()
            with profile(activities=[ProfilerActivity.CUDA]) as prof:
                for t in range(200):
                    xbuf.copy_(emb[t:t + 1]); g.replay()
                torch.cuda.synchronize()
            print(prof.key_averages().table(sort_by='cuda_time_total', row_limit=8, max_name_column_width=40))
        # tolerate extra padding dims in state for variants: compare only when same numel
        if ref_res is None:
            ref_res = (out, xs, state)
            r['exact'] = 'REF'
        else:
            ro, rx, rs = ref_res
            r['kout_exact'] = bool(torch.equal(out, ro))
            r['kout_bad_rows'] = int((out != ro).any(1).sum())
            r['resid_exact'] = bool(torch.equal(xs, rx))
            r['state_exact'] = bool(state.shape == rs.shape and torch.equal(state, rs))
            r['codes_exact'] = r['kout_exact']
        print(json.dumps(r), flush=True)
        results.append(r)
        del g, ex
        torch.cuda.empty_cache()
    res = dict(gpu=torch.cuda.get_device_name(0), tokens=N, results=results)
    print(json.dumps(res))
    if args.json: Path(args.json).write_text(json.dumps(res))
if __name__ == '__main__': main()
