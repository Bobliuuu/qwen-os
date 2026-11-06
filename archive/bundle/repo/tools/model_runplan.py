#!/usr/bin/env python3
"""Plan the parallel model run of the E1M1 clip with the chunk ROM (host-only, seconds: uses the C twin).

  tools/model_runplan.py --elf build/demo/qwenos-e1m1.elf --kernel-elf build/kernel-doomd.elf --disk E1.img \
      --rom-plan build/demo/crx-plan.json --frames 75 --gpus 9 --out-dir out/runplan75 [--model q4-rv1]
  append-only (extends to 10 s without changing earlier chunks):   --chunk-tokens 12000000 instead of --gpus

How it works
  * rv32_fast runs the ELF with CRXPLAN (the same window fills the model driver does) and logs, per frame marker,
    the instruction count and every disk request that still reaches the mailbox (kernel boot reads etc.).
  * A model chunk is a run of segments from one frame-marker boundary to the next, independently startable:
    tools/model_doom_qwen.py --snapshot-marker 0 --split-markers B1,B2,.. --segment-range A:B walks the host
    reference through the earlier chunks and installs the data-ROM window of the ROM chunk that contains the
    chunk's start marker (fill_drom) BEFORE the snapshot the model gets.  Segments also end at every ROM-chunk
    boundary marker, so a segment never straddles two windows.
  * Segment numbering: every disk request that reaches the mailbox, every ROM/split boundary marker and the final
    marker ends a segment (model_doom_qwen.plan); A:B is derived from that rule (verify with --plan-json on a prefix).
  * tokens = instructions x --tok-per-instr (measured 1.391 on this engine; +console echo is ~0 without --dump).
Writes out-dir/runplan.json (chunks with markers, segment range, instr, tokens, est seconds) and commands.txt.
"""
import argparse, json, os, re, subprocess, sys, tempfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def symhex(elf, name):
    out = subprocess.check_output(['readelf', '-sW', str(elf)], text=True)
    for ln in out.splitlines():
        f = ln.split()
        if len(f) >= 8 and f[-1] == name:
            return f[1].lstrip('0') or '0'
    raise SystemExit(f'{name} not in {elf}')


def host_run(args, frames_needed):
    rv = args.rv32_fast or str(HERE.parent / 'build' / 'rv32_fast')
    plan = json.loads(Path(args.rom_plan).read_text())
    binplan = Path(args.rom_plan).with_suffix('.bin')
    env = dict(os.environ, CRXBASE='%x' % plan['base'], REQLOG=tempfile.mktemp(suffix='.req'))
    if binplan.exists():
        env['CRXPLAN'] = str(binplan)
    mb = [symhex(args.kernel_elf, 'qos_input_mailbox'), symhex(args.kernel_elf, 'qos_disk_mailbox')]
    r = subprocess.run([rv, args.elf, args.disk] + mb + [tempfile.mktemp(), '4000000000'], env=env,
                       capture_output=True, text=True)
    err = r.stderr
    fr = [int(m.group(1)) for m in re.finditer(r'^frame \d+ at (\d+) delta', err, re.M)]
    a = np.fromfile(env['REQLOG'], dtype='<u4').reshape(-1, 5)
    os.unlink(env['REQLOG'])
    crx = re.findall(r'CRX chunk (\d+)-(\d+) reqs=(\d+)', err)
    return fr, a[:, 4].astype(int), [(int(x), int(y), int(z)) for x, y, z in crx], plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--elf', required=True); ap.add_argument('--kernel-elf', required=True)
    ap.add_argument('--disk', required=True); ap.add_argument('--rom-plan', required=True)
    ap.add_argument('--rv32-fast', default=None)
    ap.add_argument('--frames', type=int, default=75, help='frame markers the model must complete (75 = 5 s at 15 fps)')
    ap.add_argument('--gpus', type=int, default=0, help='balanced split into this many chunks (NOT append-only)')
    ap.add_argument('--chunk-tokens', type=int, default=0, help='append-only: close a chunk at the first marker where it has >= this many tokens')
    ap.add_argument('--max-chunk-tokens', type=int, default=0, help='append-only: close a chunk BEFORE the next frame would exceed this many tokens (critical path = biggest chunk)')
    ap.add_argument('--cold-split', action='store_true', help='split the cold-boot/level-load stretch (marker 0 -> 1) at instruction counts if it exceeds --max-chunk-tokens')
    ap.add_argument('--tok-per-instr', type=float, default=1.391)
    ap.add_argument('--tok-per-s', type=float, default=3200.0)
    ap.add_argument('--model', default='MODEL_DIR'); ap.add_argument('--out-dir', required=True)
    ap.add_argument('--sym-elf', default=None, help='engine doomd.elf with q_stop_at/q_stop_here (build/lr-demo/doomd.elf); REQUIRED for splitting a ROM chunk')
    ap.add_argument('--plan-out', default=None, help='also write the fleet chunk plan (name target A:B [extra]) here')
    ap.add_argument('--extra', default='', help='extra model_doom_qwen.py args (e.g. --keys ...)')
    a = ap.parse_args()
    if sum(bool(x) for x in (a.gpus, a.chunk_tokens, a.max_chunk_tokens)) != 1:
        ap.error('give exactly one of --gpus / --chunk-tokens / --max-chunk-tokens')
    fr, req_marks, crx, plan = host_run(a, a.frames)
    F = a.frames
    if len(fr) < F:
        sys.exit(f'only {len(fr)} frames in the run')
    steps = [0] + fr[:F]            # steps[k] = instructions to reach marker k (k=0 -> start)
    tpi = a.tok_per_instr
    tok_iv = np.diff(steps) * tpi   # tokens of marker interval k-1 -> k
    rom_b = sorted({c['lo'] for c in plan['chunks'] if 0 < c['lo'] < F})
    first = [1]   # cold boot (snapshot at marker 0): the first marker always ends a segment (the stop hook is wiped by the takeover)
    budget = a.max_chunk_tokens or a.chunk_tokens
    # --- chunk boundaries: ('step', s) inside the cold-boot/level-load interval, ('marker', k) after it ---
    bnd = [('marker', 0)]
    csteps = []
    if a.cold_split and tok_iv[0] > (a.max_chunk_tokens or 1e30):
        k = int(np.ceil(tok_iv[0] / a.max_chunk_tokens))
        csteps = [int(round(steps[1] * i / k)) for i in range(1, k)]
        bnd += [('step', x) for x in csteps]
    if a.max_chunk_tokens:            # close BEFORE a marker interval would push the chunk over the budget (append-only)
        acc, start = 0.0, 1
        for k in range(1, F + 1):
            t = tok_iv[k - 1] if k > 1 or not csteps else tok_iv[0] - (csteps[-1]) * tpi
            if k == 1:
                bnd.append(('marker', 1)); acc = 0.0; continue   # chunk boundary at the first marker (cold stretch ends there)
            if acc > 0 and acc + t > budget:
                bnd.append(('marker', k - 1)); acc = 0.0
            acc += t
        # note: the loop above appends boundary k-1 when interval k does not fit
    elif a.chunk_tokens:
        acc = 0.0
        for k in range(1, F):
            acc += tok_iv[k - 1]
            if acc >= a.chunk_tokens:
                bnd.append(('marker', k)); acc = 0.0
    else:
        tot = tok_iv.sum(); n = a.gpus; goal = tot / n
        cum = np.cumsum(tok_iv)
        for j in range(1, n):
            k = int(np.searchsorted(cum, goal * j)) + 1
            if 0 < k < F and ('marker', k) not in bnd:
                bnd.append(('marker', k))
    bnd = [b for i, b in enumerate(bnd) if b not in bnd[:i]]
    splits = sorted({k for t, k in bnd if t == 'marker' and k > 0})
    allm = sorted(set(rom_b) | set(splits) | set(first))
    def key(b):                       # position of a boundary among the segment-ending events
        return float(b[1]) if b[0] == 'marker' else 0.7 + 0.0001 * csteps.index(b[1])
    evkeys = sorted([float(f) + 0.5 for f in req_marks if f < F] + [key(('step', x)) for x in csteps]
                    + [float(b) for b in allm] + [float(F)])
    def seg_index(k):                 # first segment starting at/after boundary key k
        return sum(1 for e in evkeys if e <= k) + 1
    def at(b): return steps[b[1]] if b[0] == 'marker' else b[1]
    chunks = []
    ends = bnd[1:] + [('marker', F)]
    for i, (b0, b1) in enumerate(zip(bnd, ends)):
        A = seg_index(key(b0)) if i else 1
        B = len(evkeys) + 1 if b1 == ('marker', F) else seg_index(key(b1))
        ins = at(b1) - at(b0)
        tok = ins * tpi
        m0 = b0[1] if b0[0] == 'marker' else 0
        m1 = b1[1] if b1[0] == 'marker' else 0
        pauses = int(sum(1 for f in req_marks if (f < F and (i == 0 or m0 <= f < m1)) and (i or f == 0))) if True else 0
        pauses = int(((req_marks == 0).sum()) if i == 0 else sum(1 for f in req_marks if m0 <= f < m1 and b0[0] == 'marker' and f > 0 or False))
        rc = [j for j, c in enumerate(plan['chunks']) if c['lo'] <= m0 < c['hi']][0]
        chunks.append(dict(chunk=i, marker_start=m0, marker_end=m1 if b1[0] == 'marker' else m0,
                           step_start=int(at(b0)), step_end=int(at(b1)),
                           frames=(m1 - m0) if b1[0] == 'marker' else 0, rom_chunk_at_start=rc,
                           segment_range=f'{A}:{B}', n_segments=B - A, disk_pauses=pauses, instr=int(ins),
                           tokens=int(tok), est_seconds=round(tok / a.tok_per_s)))
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    sp = ",".join(map(str, allm)); ss = ",".join(map(str, csteps))
    base = (f'python3 tools/model_doom_qwen.py {a.model} --elf {a.elf} --kernel-elf {a.kernel_elf} --disk {a.disk} '
            f'--snapshot-marker 0 --frames {F} --rom-plan {a.rom_plan} --split-markers {sp}'
            f'{" --split-steps " + ss if ss else ""}{" --sym-elf " + a.sym_elf if a.sym_elf else ""} {a.extra}').strip()
    cmds = [f'{base} --segment-range {c["segment_range"]} --out out/chunk{c["chunk"]}.bin --result-json out/chunk{c["chunk"]}.json'
            for c in chunks]
    if a.plan_out:
        common = base.split(' --snapshot-marker', 1)[1]
        lines = ['# name target segment-range extra   (tools/model_runplan.py: frames=%d, %d chunks, max chunk %d tokens, tok/instr %.3f)'
                 % (F, len(chunks), max(c['tokens'] for c in chunks), tpi)]
        for c in chunks:
            lines.append(f'c{c["chunk"]:02d} boot-frame {c["segment_range"]} --snapshot-marker{common}')
        Path(a.plan_out).write_text('\n'.join(lines) + '\n')
    rep = dict(frames=F, tok_per_instr=tpi, tok_per_s_assumed=a.tok_per_s, rom_boundaries=rom_b,
               split_markers=allm, split_steps=csteps, max_chunk_tokens_budget=a.max_chunk_tokens,
               total_instr=int(steps[F]), total_tokens=int(steps[F] * tpi),
               in_run_disk_requests=int((req_marks < F).sum()), crx_check=crx, n_chunks=len(chunks),
               max_chunk_tokens=max(c['tokens'] for c in chunks), chunks=chunks,
               wall_est_parallel_s=max(c['est_seconds'] for c in chunks))
    (out / 'runplan.json').write_text(json.dumps(rep, indent=1))
    (out / 'commands.txt').write_text('\n'.join(cmds) + '\n')
    print(json.dumps({k: v for k, v in rep.items() if k != 'chunks'}))
    for c in chunks:
        print(c)


if __name__ == '__main__':
    main()
