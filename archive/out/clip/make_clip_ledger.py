#!/usr/bin/env python3
"""Regenerate README.md (incl. the per-frame verification table) of the 3 s DOOM clip.
Re-run any time:  python3 make_clip_ledger.py
Inputs: out/model/runplan_clip3s.json, out/model/chunks/{cNN,prod1,prod1p}/cNN/result.json, frame_instr.json.
A chunk counts as verified ONLY if its result.json has mode == MODEL, every segment_detail entry has ok=true,
no 'divergence' key, and its segment_range matches the plan line in out/model/chunks.plan."""
import json, glob, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
CH = f'{OUT}/model/chunks'
plan = json.load(open(f'{OUT}/model/runplan_clip3s.json'))
fi = json.load(open(f'{HERE}/frame_instr.json'))
planseg = {}
for l in open(f'{OUT}/model/chunks.plan'):
    p = l.split()
    if p and re.match(r'c\d\d$', p[0]): planseg[p[0]] = p[2]

def lane(r):
    g = r.get('gpu', ''); h = r.get('host', '')
    if h == 'modal': return 'Modal A100'
    if 'A10G' in g: return 'AWS A10G'
    if 'A100' in g: return 'Lambda A100'
    return g or '?'

def load(c):
    """first valid MODEL result in priority order; returns (result, dir, ok, why, dups)"""
    found = []
    for d in ('.', 'prod1p', 'prod1'):
        f = f'{CH}/{d}/{c}/result.json'
        if not os.path.exists(f): continue
        try: r = json.load(open(f))
        except Exception: continue
        if r.get('mode') != 'MODEL': continue
        why = []
        if 'divergence' in r: why.append('divergence key')
        sd = r.get('segment_detail') or []
        if not sd or not all(s[1] is True for s in sd): why.append('segment not ok')
        if r.get('segment_range') != planseg.get(c): why.append('segment_range != plan')
        found.append((r, d, not why, ','.join(why)))
    if not found: return None, None, False, 'no result yet', 0
    best = next((x for x in found if x[2]), found[0])
    return best[0], best[1], best[2], best[3], len(found) - 1

res = {}
for ch in plan['chunks']:
    c = 'c%02d' % ch['chunk']
    res[c] = load(c)

def chunks_for_frame(m):
    s = [c for c in plan['chunks'] if c['marker_start'] < m <= c['marker_end']]
    # zero-frame prefix chunks directly before (same marker, split by step count)
    pre = [c for c in plan['chunks'] if c['marker_start'] == c['marker_end'] == m - 1 and c['step_end'] <= s[0]['step_start'] + 0]
    return pre + s

rows = []; nver = 0
for f in fi:
    cs = chunks_for_frame(f['marker'])
    names = ['c%02d' % c['chunk'] for c in cs]
    oks = [res[n][2] for n in names]
    lanes = sorted({lane(res[n][0]) for n in names if res[n][0]})
    v = all(oks); nver += v
    rows.append((f, names, lanes, v, [res[n][3] for n in names if not res[n][2]]))

done = [c for c in res if res[c][2]]
tok = sum(r[0]['model_chip_tokens'] for r in res.values() if r[2])
instr_done = sum(r[0]['instructions'] for r in res.values() if r[2])
lane_n = {}
for c in done: lane_n[lane(res[c][0])] = lane_n.get(lane(res[c][0]), 0) + 1
lane_s = {}
for c in done: lane_s[lane(res[c][0])] = lane_s.get(lane(res[c][0]), 0) + res[c][0].get('wall_seconds', 0)

T = []
T.append('| frame | game tic (drawn in) | instr this frame (prod ELF) | chunk(s) | lane | model-verified |')
T.append('|---:|---:|---:|---|---|---|')
for f, names, lanes, v, why in rows:
    T.append(f"| {f['frame']:02d} | {f['tic']} | {f['instr']:,} | {'+'.join(names)} | {' / '.join(lanes) or '-'} | {'**yes**' if v else 'no' + (' (' + '; '.join(why) + ')' if why else '')} |")
C = ['| chunk | markers | segment range | instr | chip tokens (model) | lane / host | wall s | result dir | status |', '|---|---|---|---:|---:|---|---:|---|---|']
for ch in plan['chunks']:
    c = 'c%02d' % ch['chunk']; r, d, ok, why, dup = res[c]
    if r:
        C.append(f"| {c} | {ch['marker_start']}->{ch['marker_end']} | {r['segment_range']} | {r['instructions']:,} | {r['model_chip_tokens']:,} | {lane(r)} ({r.get('host')}) | {r.get('wall_seconds')} | {'chunks/' + (d if d != '.' else c)}{'/'+c if d != '.' else ''}{' (+%d duplicate run)' % dup if dup else ''} | {'ok, MODEL' if ok else 'NOT OK: ' + why} |")
    else:
        C.append(f"| {c} | {ch['marker_start']}->{ch['marker_end']} | {ch['segment_range']} | {ch['instr']:,} | (planned {ch['tokens']:,}) | - | - | - | pending / no result |")

summary = (f"{len(done)}/{plan['n_chunks']} chunks ok (MODEL), {nver}/45 frames model-verified, {45 - nver} frames emulator-only (chunk pending). "
           f"Chip tokens in completed chunks: {tok:,} (plan total {plan['total_tokens']:,}); instructions in completed chunks: {instr_done:,} of {plan['total_instr']:,}.")
lanes_txt = '; '.join(f'{k}: {n} chunks, {lane_s[k]:.0f} s model wall' for k, n in sorted(lane_n.items()))

md = open(f'{HERE}/README.template.md').read()
md = (md.replace('@@SUMMARY@@', summary).replace('@@LANES@@', lanes_txt).replace('@@FRAMETABLE@@', '\n'.join(T))
        .replace('@@CHUNKTABLE@@', '\n'.join(C)).replace('@@NVER@@', str(nver)).replace('@@NEMU@@', str(45 - nver))
        .replace('@@NCHUNK@@', str(len(done))).replace('@@TOK@@', f'{tok:,}'))
open(f'{HERE}/README.md', 'w').write(md)
print(summary); print(lanes_txt)
if '--prov' in sys.argv:
    print(f"| clip qwenos-doom-3s | 45 frames, 15 fps, 3.0 s | 35 chunks planned ({len(done)} ok MODEL), 1 emulator pixel run | {nver}/45 | {45-nver}/45 |")
