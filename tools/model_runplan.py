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
    ap.add_argument('--tok-per-instr', type=float, default=1.391)
    ap.add_argument('--tok-per-s', type=float, default=3200.0)
    ap.add_argument('--model', default='MODEL_DIR'); ap.add_argument('--out-dir', required=True)
    ap.add_argument('--sym-elf', default=None, help='engine doomd.elf with q_stop_at/q_stop_here (build/lr-demo/doomd.elf); REQUIRED for splitting a ROM chunk')
    ap.add_argument('--plan-out', default=None, help='also write the fleet chunk plan (name target A:B [extra]) here')
    ap.add_argument('--extra', default='', help='extra model_doom_qwen.py args (e.g. --keys ...)')
    a = ap.parse_args()
    if bool(a.gpus) == bool(a.chunk_tokens):
        ap.error('give exactly one of --gpus / --chunk-tokens')
    fr, req_marks, crx, plan = host_run(a, a.frames)
    F = a.frames
    if len(fr) < F:
        sys.exit(f'only {len(fr)} frames in the run')
    steps = [0] + fr[:F]            # steps[k] = instructions to reach marker k (k=0 -> start)
    instr_iv = np.diff(steps)       # instr of marker interval k-1 -> k  (index k-1)
    tok_iv = instr_iv * a.tok_per_instr
    rom_b = sorted({c['lo'] for c in plan['chunks'] if 0 < c['lo'] < F})
    first = [1]   # cold boot (snapshot at marker 0): the first marker always ends a segment (the stop hook is wiped by the takeover)
    # chunk boundaries (markers)
    if a.chunk_tokens:
        bounds, acc = [0], 0.0
        for k in range(1, F + 1):
            acc += tok_iv[k - 1]
            if acc >= a.chunk_tokens and k < F:
                bounds.append(k); acc = 0.0
    else:
        tot = tok_iv.sum(); n = a.gpus; goal = tot / n  # boundary j at the first marker where cumulative tokens >= j*goal
        cum = np.cumsum(tok_iv); bounds = [0]
        for j in range(1, n):
            k = int(np.searchsorted(cum, goal * j)) + 1
            if bounds[-1] < k < F:
                bounds.append(k)
    splits = sorted(set(bounds[1:]))
    # segment events: disk requests (key f+0.5 for frames-count f; only those inside the run), boundary markers
    evkeys = sorted([float(f) + 0.5 for f in req_marks if f < F] + [float(b) for b in set(rom_b) | set(splits) | set(first)] + [float(F)])
    def seg_index(marker):            # first segment starting at/after `marker` boundary
        return sum(1 for k in evkeys if k <= marker) + 1
    chunks = []
    ends = bounds[1:] + [F]
    for i, (b0, b1) in enumerate(zip(bounds, ends)):
        A, B = seg_index(b0), seg_index(b1)
        if b1 == F:
            B = len(evkeys) + 1
        ins = steps[b1] - steps[b0]
        tok = ins * a.tok_per_instr
        pauses = int(sum(1 for f in req_marks if b0 <= f < b1)) if b0 else int(sum(1 for f in req_marks if f < b1))
        rc = [j for j, c in enumerate(plan['chunks']) if c['lo'] <= b0 < c['hi']][0]
        chunks.append(dict(chunk=i, marker_start=b0, marker_end=b1, frames=b1 - b0, rom_chunk_at_start=rc,
                           segment_range=f'{A}:{B}', n_segments=B - A, disk_pauses=pauses, instr=int(ins),
                           tokens=int(tok), est_seconds=round(tok / a.tok_per_s)))
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    base = (f'python3 tools/model_doom_qwen.py {a.model} --elf {a.elf} --kernel-elf {a.kernel_elf} --disk {a.disk} '
            f'--snapshot-marker 0 --frames {F} --rom-plan {a.rom_plan} --split-markers {",".join(map(str, sorted(set(rom_b) | set(splits) | set(first))))}'
            f'{" --sym-elf " + a.sym_elf if a.sym_elf else ""} {a.extra}').strip()
    cmds = [f'{base} --segment-range {c["segment_range"]} --out out/chunk{c["chunk"]}.bin --result-json out/chunk{c["chunk"]}.json'
            for c in chunks]
    rep = dict(frames=F, tok_per_instr=a.tok_per_instr, tok_per_s_assumed=a.tok_per_s, rom_boundaries=rom_b,
               split_markers=splits, total_instr=int(steps[F]), total_tokens=int(steps[F] * a.tok_per_instr),
               in_run_disk_requests=int((req_marks < F).sum()), crx_check=crx, chunks=chunks,
               wall_est_parallel_s=max(c['est_seconds'] for c in chunks))
    if a.plan_out:
        common = base.split(' --snapshot-marker', 1)[1]
        lines = ['# name target segment-range extra   (tools/model_runplan.py: frames=%d, %d chunks, tok/instr %.3f)' % (F, len(chunks), a.tok_per_instr)]
        for c in chunks:
            lines.append(f'c{c["chunk"]:02d} boot-frame {c["segment_range"]} --snapshot-marker{common}')
        Path(a.plan_out).write_text('\n'.join(lines) + '\n')
    (out / 'runplan.json').write_text(json.dumps(rep, indent=1))
    (out / 'commands.txt').write_text('\n'.join(cmds) + '\n')
    print(json.dumps({k: v for k, v in rep.items() if k != 'chunks'}))
    for c in chunks:
        print(c)


if __name__ == '__main__':
    main()
