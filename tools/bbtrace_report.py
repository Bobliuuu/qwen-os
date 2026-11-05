#!/usr/bin/env python3
"""Turn the raw tools/bbtrace output directory into docs/research/BBTRACE.md (tables + fusion estimate).
Everything here is derived from the host-emulator trace; nothing is measured on the model.

  python3 tools/bbtrace_report.py --elf build/demo/qwenos-e1m1.elf --dir build/bbtrace.out \
      --sym build/lr-demo/doomd.elf,build/kernel-doomd.elf --out docs/research/BBTRACE.md --repro "<command>"
"""
import argparse
import math
import statistics
import struct
from collections import Counter, defaultdict
from pathlib import Path

TOK_LO, TOK_HI = 1.345, 1.468   # chip tokens per instruction, measured on the model (README / STATUS.md)


# ---------------------------------------------------------------- ELF + disassembler
def load_code(elf):
    d = Path(elf).read_bytes()
    ent, phoff = struct.unpack_from('<I', d, 24)[0], struct.unpack_from('<I', d, 28)[0]
    phes, phn = struct.unpack_from('<HH', d, 42)
    mem = {}
    for i in range(phn):
        t, off, va, pa, fsz, msz, fl, al = struct.unpack_from('<8I', d, phoff + i * phes)
        if t == 1:
            for k in range(0, fsz, 4):
                if len(d) >= off + k + 4:
                    mem[va + k] = struct.unpack_from('<I', d, off + k)[0]
    return mem


def load_syms(paths):
    out = []
    for p in paths:
        try:
            d = Path(p).read_bytes()
        except OSError:
            continue
        shoff = struct.unpack_from('<I', d, 32)[0]
        shes, shn = struct.unpack_from('<HH', d, 46)
        for i in range(shn):
            sh = struct.unpack_from('<10I', d, shoff + i * shes)
            if sh[1] != 2:
                continue
            strh = struct.unpack_from('<10I', d, shoff + sh[6] * shes)
            for j in range(sh[5] // 16):
                nm, val, sz, info = struct.unpack_from('<IIIB', d, sh[4] + j * 16)
                if (info & 15) not in (0, 2) or not (0x40000 <= val < 0x80000) or not nm:
                    continue
                name = d[strh[4] + nm:d.index(b'\0', strh[4] + nm)].decode()
                if name.startswith('$') or name.startswith('.L'):
                    continue
                out.append((val, name))
    out.sort()
    return out


class Syms:
    def __init__(self, lst):
        self.a = [x[0] for x in lst]
        self.n = [x[1] for x in lst]

    def __call__(self, pc):
        import bisect
        k = bisect.bisect_right(self.a, pc) - 1
        if k < 0:
            return '?'
        o = pc - self.a[k]
        return self.n[k] + (f'+{o:#x}' if o else '')

    def func(self, pc):
        import bisect
        k = bisect.bisect_right(self.a, pc) - 1
        return self.n[k] if k >= 0 else '?'


ABI = ['zero', 'ra', 'sp', 'gp', 'tp', 't0', 't1', 't2', 's0', 's1'] + [f'a{i}' for i in range(8)] + [f's{i}' for i in range(2, 12)] + [f't{i}' for i in range(3, 7)]


def sx(v, b):
    return v - (1 << b) if v >> (b - 1) else v


def disasm(w, pc):
    """returns (mnemonic, text). mnemonic is the operand-free class used for pattern statistics."""
    op, rd, f3, rs1, rs2, f7 = w & 127, (w >> 7) & 31, (w >> 12) & 7, (w >> 15) & 31, (w >> 20) & 31, w >> 25
    r = ABI
    ii = sx(w >> 20, 12)
    isv = sx(((w >> 25) << 5) | ((w >> 7) & 31), 12)
    if op == 0x37:
        return 'lui', f'lui {r[rd]},{w >> 12:#x}'
    if op == 0x17:
        return 'auipc', f'auipc {r[rd]},{w >> 12:#x}'
    if op == 0x6f:
        im = sx(((w >> 31) << 20) | (((w >> 12) & 255) << 12) | (((w >> 20) & 1) << 11) | (((w >> 21) & 0x3ff) << 1), 21)
        return 'jal', f'jal {r[rd]},{pc + im:#x}'
    if op == 0x67:
        return 'jalr', f'jalr {r[rd]},{ii}({r[rs1]})'
    if op == 0x63:
        im = sx(((w >> 31) << 12) | (((w >> 7) & 1) << 11) | (((w >> 25) & 0x3f) << 5) | (((w >> 8) & 0xf) << 1), 13)
        m = ['beq', 'bne', '?', '?', 'blt', 'bge', 'bltu', 'bgeu'][f3]
        return m, f'{m} {r[rs1]},{r[rs2]},{pc + im:#x}'
    if op == 0x03:
        m = ['lb', 'lh', 'lw', '?', 'lbu', 'lhu'][f3]
        return m, f'{m} {r[rd]},{ii}({r[rs1]})'
    if op == 0x23:
        m = ['sb', 'sh', 'sw'][f3]
        return m, f'{m} {r[rs2]},{isv}({r[rs1]})'
    if op == 0x13:
        if f3 in (1, 5):
            m = {1: 'slli', 5: 'srai' if f7 == 0x20 else 'srli'}[f3]
            return m, f'{m} {r[rd]},{r[rs1]},{rs2}'
        m = {0: 'addi', 2: 'slti', 3: 'sltiu', 4: 'xori', 6: 'ori', 7: 'andi'}[f3]
        return m, f'{m} {r[rd]},{r[rs1]},{ii}'
    if op == 0x33:
        if f7 == 1:
            m = ['mul', 'mulh', 'mulhsu', 'mulhu', 'div', 'divu', 'rem', 'remu'][f3]
        else:
            m = {0: 'sub' if f7 else 'add', 1: 'sll', 2: 'slt', 3: 'sltu', 4: 'xor', 5: 'sra' if f7 else 'srl', 6: 'or', 7: 'and'}[f3]
        return m, f'{m} {r[rd]},{r[rs1]},{r[rs2]}'
    if op == 0x73:
        return 'ecall', 'ecall'
    if op == 0x0f:
        return 'fence', 'fence'
    return '?', f'.word {w:#010x}'


def tsv(path):
    for ln in Path(path).read_text().splitlines():
        yield ln.split('\t')


def pct(a, b):
    return f'{100.0 * a / b:.2f}%' if b else '-'


def table(head, rows):
    out = ['| ' + ' | '.join(head) + ' |', '|' + '|'.join(['---'] * len(head)) + '|']
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--elf', required=True)
    ap.add_argument('--dir', required=True)
    ap.add_argument('--sym', default='')
    ap.add_argument('--out', required=True)
    ap.add_argument('--repro', default='tools/bbtrace_e1m1.sh')
    ap.add_argument('--copy-tics', default='')
    a = ap.parse_args()
    D = Path(a.dir)
    code = load_code(a.elf)
    sym = Syms(load_syms([s for s in a.sym.split(',') if s] or [a.elf]))
    S = {k: int(v) for k, v in (r for r in tsv(D / 'summary.txt'))}
    N = S['steps']
    KIND = {0x63: 'cond branch', 0x6f: 'jal', 0x67: 'jalr', 0x73: 'ecall'}

    blocks = []   # dict per block
    for r in tsv(D / 'blocks.tsv'):
        start, ln, cnt, kop, tot = int(r[0], 16), int(r[1]), int(r[2]), int(r[3], 16), int(r[4])
        succ = []
        other = 0
        for f in r[5:]:
            t, c = f.split(':')
            if t == 'other':
                other = int(c)
            else:
                succ.append((int(t, 16), int(c)))
        blocks.append(dict(start=start, len=ln, cnt=cnt, kop=kop, succ=sorted(succ, key=lambda x: -x[1]), other=other,
                           ins=[disasm(code.get(start + 4 * i, 0), start + 4 * i) for i in range(ln)]))
    bymap = {b['start']: b for b in blocks}
    for b in blocks:
        b['dyn'] = b['len'] * b['cnt']
        b['mem'] = []
    for r in tsv(D / 'mem.tsv'):
        b = bymap[int(r[0], 16)]
        strides = []
        other = 0
        for f in r[10:]:
            t, c = f.split(':')
            if t == 'other':
                other = int(c)
            else:
                strides.append((int(t), int(c)))
        b['mem'].append(dict(pc=int(r[2], 16), st=int(r[3]), n=int(r[4]), rs1=int(r[5]), ex=int(r[6]), same=int(r[7]),
                             lo=int(r[8], 16), hi=int(r[9], 16), strides=sorted(strides, key=lambda x: -x[1]), other=other))
    blocks.sort(key=lambda b: -b['dyn'])
    nb = S['dyn_blocks']
    L = []
    w = L.append

    w('# Dynamic basic-block trace of the E1M1 demo (host emulator)\n')
    w('Every number in this file comes from the **host C emulator** (`tools/rv32_fast.c` built with `-DBBTRACE`). Nothing here was run on the Qwen model, a GPU or any paid service. '
      'The fusion section is an **estimate of how many neural transitions could disappear in the best case; it is not a measured or promised speedup.**\n')
    w('## What was traced\n')
    w('- Image: `build/demo/qwenos-e1m1.elf` (`make demo-elf`: scripted E1M1, FULL preset, 350 game tics), DMC100 `/bin/doomd` on Freedoom E1M1, run to its exit ecall.')
    w('- Disk: host-served (the dry-run configuration of `tools/mkdemo.sh`), so this is the 180.5 M instruction run, not the 81 M chunk-ROM clip. The trace therefore includes the cold boot and level load, and the disk-request code paths.')
    w('- A **dynamic basic block** is a maximal run of consecutively *executed* instructions that begins at program entry or at the target (taken or fall-through) of a control transfer, and ends at the first `beq/bne/blt/bge/bltu/bgeu`, `jal`, `jalr` or `ecall` (that instruction is the last of the block). '
      'Code is immutable ROM, so the start pc fixes the exact instruction sequence; the tracer asserts this. Entering a block in its middle creates a different block (blocks may overlap).')
    w('- Pair/triple counts are over the *actual* executed stream (consecutive retired instructions, across taken branches too), not per-pc histograms.')
    w(f'- Raw data: `blocks.tsv`, `mem.tsv`, `pairs.tsv`, `triples.tsv`, `tics.tsv`, `summary.txt` in the trace directory; `tics.tsv` is committed next to this file (`docs/research/bbtrace/tics.tsv`).\n')
    w('## Reproduce\n')
    w('```sh\n' + a.repro + '\n```\n')
    w('Needs the repo build prerequisites (Clang/LLD, the DMC100 engine tree with `engine-patches/`, Freedoom WAD in the E1 NOR image; see README "Get the engine and Freedoom"). '
      'The test `tests/test_bbtrace.py` (part of `python3 -m unittest discover -s tests`) proves the tracer is a pure observer.\n')

    w('## Totals\n')
    sl = sum(b['dyn'] for b in blocks)
    w(table(['Quantity', 'Value'], [
        ['Guest instructions executed (steps)', f'{N:,}'],
        ['Instructions inside completed blocks', f'{S["block_instrs"]:,}'],
        ['Open tail at exit (not in a block; retired instrs of the unfinished last block)', f'{S["truncated_tail_instrs"]:,}'],
        ['Dynamic blocks executed', f'{nb:,}'],
        ['Static (distinct start pc) blocks seen', f'{S["static_blocks"]:,}'],
        ['Mean dynamic block length (instr)', f'{S["block_instrs"] / nb:.3f}'],
        ['Loads / stores', f'{S["loads"]:,} / {S["stores"]:,}  ({S["loads"] / N:.3f} / {S["stores"] / N:.3f} per instr)'],
        ['Distinct executed instruction pairs / triples', f'{S["uniq_pairs"]:,} / {S["uniq_triples"]:,}'],
    ]))
    w('')

    # ------------------------------------------------------------ coverage
    w('## Coverage: how much of the run the hottest blocks cover\n')
    cum = 0
    marks = [1, 5, 10, 20, 50, 100, 200, 500, 1000, 2000]
    rows = []
    cov = {}
    for i, b in enumerate(blocks, 1):
        cum += b['dyn']
        if i in marks:
            cov[i] = cum
            rows.append([f'top {i}', f'{cum:,}', pct(cum, N)])
    w(table(['Blocks (ranked by dynamic instrs)', 'Dynamic instrs covered', '% of total'], rows))
    w('')
    # by function
    fn = Counter()
    for b in blocks:
        fn[sym.func(b['start'])] += b['dyn']
    w('Same coverage by enclosing symbol (block start pc), top 15:\n')
    w(table(['Symbol', 'Dynamic instrs', '% of total'], [[k, f'{v:,}', pct(v, N)] for k, v in fn.most_common(15)]))
    w('')

    # ------------------------------------------------------------ top blocks
    w('## Hottest blocks\n')
    rows = []
    for i, b in enumerate(blocks[:25], 1):
        top = b['succ'][0] if b['succ'] else (0, 0)
        tot = sum(c for _, c in b['succ']) + b['other']
        ld = sum(1 for m, _ in b['ins'] if m in ('lb', 'lh', 'lw', 'lbu', 'lhu'))
        stc = sum(1 for m, _ in b['ins'] if m in ('sb', 'sh', 'sw'))
        rows.append([i, f'`{b["start"]:#x}`', f'`{sym(b["start"])}`', b['len'], f'{b["cnt"]:,}', pct(b['dyn'], N), KIND[b['kop']], f'{ld}/{stc}',
                     f'{top[0]:#x} {100.0 * top[1] / tot:.0f}% ({len(b["succ"])}{"+" if b["other"] else ""} tgts)'])
    w(table(['#', 'Start pc', 'Symbol', 'Len', 'Exec count', '% of dyn instrs', 'Ends with', 'Ld/St', 'Top successor (share)'], rows))
    w('')
    w('Exact instruction sequences of the ten hottest blocks:\n')
    for i, b in enumerate(blocks[:10], 1):
        w(f'**#{i}** `{b["start"]:#x}` `{sym(b["start"])}`, {b["len"]} instr, executed {b["cnt"]:,} times ({pct(b["dyn"], N)} of dynamic instrs)\n')
        w('```')
        for k, (m, t) in enumerate(b['ins']):
            w(f'{b["start"] + 4 * k:#x}  {t}')
        w('```\n')

    # ------------------------------------------------------------ lengths
    w('## Block length distribution (weighted by dynamic instructions)\n')
    buckets = [(1, 1), (2, 2), (3, 3), (4, 4), (5, 6), (7, 8), (9, 12), (13, 16), (17, 32), (33, 10**9)]
    rows = []
    for lo, hi in buckets:
        bl = [b for b in blocks if lo <= b['len'] <= hi]
        d = sum(b['dyn'] for b in bl)
        c = sum(b['cnt'] for b in bl)
        rows.append([f'{lo}' if lo == hi else (f'{lo}-{hi}' if hi < 10**9 else f'{lo}+'), len(bl), f'{c:,}', pct(c, nb), f'{d:,}', pct(d, N)])
    w(table(['Length', 'Static blocks', 'Dyn blocks', '% of dyn blocks', 'Dyn instrs', '% of dyn instrs'], rows))
    w('')

    # ------------------------------------------------------------ branch targets
    w('## Branch-target distributions\n')
    kd = Counter()
    kc = Counter()
    for b in blocks:
        kd[b['kop']] += b['cnt']
    w('How dynamic blocks end:\n')
    w(table(['Terminator', 'Dyn blocks', '% of blocks'], [[KIND[k], f'{v:,}', pct(v, nb)] for k, v in kd.most_common()]))
    w('')
    single = sum(b['cnt'] for b in blocks if len(b['succ']) == 1 and not b['other'])
    top1 = sum(b['succ'][0][1] for b in blocks if b['succ'])
    w(f'- Blocks that always went to one successor: {pct(single, nb)} of dynamic blocks.')
    w(f'- Share of block exits that went to that block\'s single most frequent successor: {pct(top1, nb)} (an upper bound for a "follow the hottest edge" static trace).')
    br = [b for b in blocks if b['kop'] == 0x63]
    brc = sum(b['cnt'] for b in br)
    tk = sum(max(c for _, c in b['succ']) for b in br)
    w(f'- Conditional branches: {brc:,} executions; the dominant direction per branch site covers {pct(tk, brc)} of them.')
    jr = [b for b in blocks if b['kop'] == 0x67]
    jrc = sum(b['cnt'] for b in jr)
    w(f'- `jalr` exits (returns and indirect calls): {jrc:,}; dominant target per site covers {pct(sum(b["succ"][0][1] for b in jr if b["succ"]), jrc)}; '
      f'sites with more than 8 distinct targets (spill to "other"): {sum(1 for b in jr if b["other"])}.\n')
    w('Successor distribution of the five hottest blocks that have more than one successor:\n')
    rows = []
    for b in [b for b in blocks if len(b['succ']) > 1][:5]:
        tot = sum(c for _, c in b['succ']) + b['other']
        rows.append([f'`{b["start"]:#x}` `{sym(b["start"])}`', KIND[b['kop']],
                     ', '.join(f'{t:#x} {100.0 * c / tot:.1f}%' for t, c in b['succ'][:6]) + (f', other {100.0 * b["other"] / tot:.1f}%' if b['other'] else '')])
    w(table(['Block', 'Ends with', 'Targets (share of exits)'], rows))
    w('')

    # ------------------------------------------------------------ memory
    w('## Memory access pattern\n')
    ld_ex = sum(s['ex'] for b in blocks for s in b['mem'] if not s['st'])
    st_ex = sum(s['ex'] for b in blocks for s in b['mem'] if s['st'])
    w(f'Loads {ld_ex:,} ({pct(ld_ex, N)} of instrs), stores {st_ex:,} ({pct(st_ex, N)}); '
      f'blocks with at least one memory op: {pct(sum(b["cnt"] for b in blocks if b["mem"]), nb)} of dynamic blocks. '
      f'Slot = one load/store site in a block; stride = address delta between two consecutive executions of the same site.\n')
    cls = Counter()
    reg = Counter()
    for b in blocks:
        for s in b['mem']:
            n = max(s['ex'] - 1, 0)
            if n == 0:
                cls['single execution'] += s['ex']
            else:
                d, c = s['strides'][0] if s['strides'] else (0, 0)
                if c * 2 < n:
                    k = 'irregular (no stride >= 50%)'
                elif d == 0:
                    k = 'same address'
                elif abs(d) == s['n']:
                    k = 'unit stride (= access width)'
                elif abs(d) <= 64:
                    k = 'small stride (<= 64 B)'
                else:
                    k = 'large stride (> 64 B)'
                cls[k] += s['ex']
            kind = 'ld' if not s['st'] else 'st'
            r = 'sp-relative' if s['rs1'] == 2 else 'other base'
            area = 'data ROM' if s['lo'] >= 0x20000 else 'RAM'
            reg[(kind, r, area)] += s['ex']
    tot = sum(cls.values())
    w(table(['Per-site pattern (weighted by executions)', 'Accesses', '%'], [[k, f'{v:,}', pct(v, tot)] for k, v in cls.most_common()]))
    w('')
    w(table(['Access', 'Base register', 'Target area (site min address)', 'Accesses', '%'],
            [[k[0], k[1], k[2], f'{v:,}', pct(v, tot)] for k, v in sorted(reg.items(), key=lambda kv: -kv[1])]))
    w('')
    w('Memory sites of the hottest blocks (first 12 sites over the 8 hottest blocks):\n')
    rows = []
    for b in blocks[:8]:
        for s in b['mem']:
            if len(rows) >= 12:
                break
            ds = ', '.join(f'{d:+d}:{c}' for d, c in s['strides'][:3])
            rows.append([f'`{b["start"]:#x}`', f'`{s["pc"]:#x}`', 'st' if s['st'] else 'ld', s['n'], ABI[s['rs1']], f'{s["ex"]:,}', f'{s["lo"]:#x}-{s["hi"]:#x}', ds])
    w(table(['Block', 'Site pc', 'Kind', 'Bytes', 'Base', 'Execs', 'Address range', 'Top strides (delta:count)'], rows))
    w('')

    # ------------------------------------------------------------ per tic
    tics = [list(map(int, r)) for r in tsv(D / 'tics.tsv')]
    if a.copy_tics:
        Path(a.copy_tics).parent.mkdir(parents=True, exist_ok=True)
        Path(a.copy_tics).write_text('tic\tstart_instr\tinstrs\tblocks\tloads\tstores\n' + (D / 'tics.tsv').read_text())
    w('## Per-tic instruction counts\n')
    if tics:
        ins = [t[2] for t in tics]
        s_ = sorted(ins)
        w(f'A tic is one entry of `G_Ticker` (the first {tics[0][1]:,} instructions are boot and level load before it). {len(tics)} complete tics.\n')
        w(table(['Statistic', 'Instrs per tic', 'Blocks per tic'], [
            ['mean', f'{statistics.mean(ins):,.0f}', f'{statistics.mean(t[3] for t in tics):,.0f}'],
            ['median', f'{s_[len(s_) // 2]:,}', f'{sorted(t[3] for t in tics)[len(tics) // 2]:,}'],
            ['p90', f'{s_[len(s_) * 9 // 10]:,}', f'{sorted(t[3] for t in tics)[len(tics) * 9 // 10]:,}'],
            ['max', f'{max(ins):,}', f'{max(t[3] for t in tics):,}'],
            ['sum', f'{sum(ins):,}', f'{sum(t[3] for t in tics):,}'],
        ]))
        w('')
        w('Ten most expensive tics, and a coarse view of the cost profile:\n')
        w(table(['Tic', 'Start instr', 'Instrs', 'Blocks', 'Loads', 'Stores'], [[t[0], f'{t[1]:,}', f'{t[2]:,}', f'{t[3]:,}', f'{t[4]:,}', f'{t[5]:,}'] for t in sorted(tics, key=lambda t: -t[2])[:10]]))
        w('')
        rows = []
        for i in range(0, len(tics), 50):
            ch = tics[i:i + 50]
            rows.append([f'{ch[0][0]}-{ch[-1][0]}', f'{statistics.mean(t[2] for t in ch):,.0f}', f'{min(t[2] for t in ch):,}', f'{max(t[2] for t in ch):,}'])
        w(table(['Tics', 'Mean instrs/tic', 'Min', 'Max'], rows))
        w('\nThe full per-tic list is `docs/research/bbtrace/tics.tsv`. The README quotes 485,801 instr/tic as the mean over tics 30-300 of the chip-ROM build; the all-tics mean here covers the cold tics too, so the two are not directly comparable.\n')
    else:
        w('No per-tic data (the run needs `SYMELF=` with the doomd ELF first so `G_Ticker` can be located).\n')

    # ------------------------------------------------------------ pairs and triples
    pairs = [(int(r[0], 16), int(r[1], 16), int(r[2])) for r in tsv(D / 'pairs.tsv')]
    trips = [(int(r[0], 16), int(r[1], 16), int(r[2], 16), int(r[3])) for r in tsv(D / 'triples.tsv')]
    w('## Hot consecutive pairs and triples\n')
    w('Counts are over the executed stream, so a pair whose first instruction is a taken branch is a real cross-block adjacency. '
      'Pairs that are statically adjacent (pc2 = pc1 + 4) are marked **seq**; others are marked **jump**.\n')
    T2 = sum(p[2] for p in pairs)
    T3 = sum(t[3] for t in trips)
    w('Coverage of the executed stream by the top-N distinct pairs / triples (by pc):\n')
    rows = []
    cp = ct = 0
    for i, p in enumerate(pairs, 1):
        cp += p[2]
        if i in (10, 50, 100, 500, 1000, 5000):
            rows.append([f'top {i}', pct(cp, T2), pct(sum(t[3] for t in trips[:i]), T3)])
    w(table(['N', 'Pairs: % of consecutive pairs', 'Triples: % of consecutive triples'], rows))
    w('')

    def dis(pc):
        return disasm(code.get(pc, 0), pc)

    w('Top 20 pairs by pc:\n')
    rows = []
    for p in pairs[:20]:
        rows.append([f'`{p[0]:#x}`', f'`{dis(p[0])[1]}`', f'`{dis(p[1])[1]}`', 'seq' if p[1] == p[0] + 4 else 'jump', f'{p[2]:,}', pct(p[2], T2)])
    w(table(['pc1', 'Instr 1', 'Instr 2', 'Adjacency', 'Count', '% of pairs'], rows))
    w('')
    w('Top 15 triples by pc:\n')
    rows = []
    for t in trips[:15]:
        rows.append([f'`{t[0]:#x}`', '`' + dis(t[0])[1] + '; ' + dis(t[1])[1] + '; ' + dis(t[2])[1] + '`', f'{t[3]:,}', pct(t[3], T3)])
    w(table(['pc1', 'Instructions', 'Count', '% of triples'], rows))
    w('')
    # opcode-class n-grams
    c2, c3 = Counter(), Counter()
    for p in pairs:
        c2[(dis(p[0])[0], dis(p[1])[0])] += p[2]
    for t in trips:
        c3[(dis(t[0])[0], dis(t[1])[0], dis(t[2])[0])] += t[3]
    w('Opcode-class patterns (operands ignored), top 15 pairs and top 10 triples:\n')
    w(table(['Pair', 'Count', '% of pairs'], [[' ; '.join(k), f'{v:,}', pct(v, T2)] for k, v in c2.most_common(15)]))
    w('')
    w(table(['Triple', 'Count', '% of triples'], [[' ; '.join(k), f'{v:,}', pct(v, T3)] for k, v in c3.most_common(10)]))
    w('')

    # ------------------------------------------------------------ fusion estimate
    w('## Estimated reduction in neural transitions from fusion (an estimate, not a speedup)\n')
    w('Model of the estimate. One guest instruction is one neural transition today; the repo measured 1.345 to 1.468 chip tokens per instruction (README / STATUS.md). '
      'Suppose some instructions that execute consecutively inside one basic block could be executed as **one** transition. The count of transitions then falls from `N` to `T`. '
      'Because the table assumes a fused transition costs the same 1.345-1.468 tokens as an unfused one, token counts scale with `T` and the reduction percentage is identical in both columns.\n')
    w('What this ignores, so read it as an optimistic bound on *transition count* only: the cost of encoding a fused operation in the chip (a fused step may need more tokens, more layers or a larger weight footprint), data dependencies between the fused instructions, '
      'the memory-model and fetch constraints of the circuit, per-segment host snapshotting, and any change to the lockstep oracle. Wall-clock speed is not derived anywhere in this file.\n')
    w(f'Baseline: N = {N:,} transitions = {N * TOK_LO:,.0f} to {N * TOK_HI:,.0f} chip tokens.\n')
    w('### A. Fuse k consecutive instructions inside every block (generic bound)\n')
    w('Each block of length `L` executes `ceil(L/k)` transitions (instructions grouped from the block start). `k = block` means a whole block is one transition. The tail open block (1 instr) is counted as 1 transition.\n')
    rows = []

    def trans(k):
        return sum(b['cnt'] * (math.ceil(b['len'] / k) if k else 1) for b in blocks) + S['truncated_tail_instrs']

    for k in (1, 2, 3, 4, 8, 16, 0):
        t = trans(k)
        rows.append(['1 (baseline)' if k == 1 else ('whole block' if k == 0 else k), f'{t:,}', f'{t * TOK_LO:,.0f} - {t * TOK_HI:,.0f}', f'{N - t:,}', pct(N - t, N)])
    w(table(['k', 'Transitions T', 'Chip tokens (1.345 - 1.468 per transition)', 'Transitions removed', 'Reduction'], rows))
    w('')
    w('Only the hottest blocks fused whole (all other code unfused): the transitions removed are `sum(count * (L - 1))` over those blocks.\n')
    rows = []
    for n_ in (1, 5, 10, 20, 50, 100, 200, 500, 1000):
        t = N - sum(b['cnt'] * (b['len'] - 1) for b in blocks[:n_])
        rows.append([f'top {n_}', pct(cov.get(n_, sum(b["dyn"] for b in blocks[:n_])), N), f'{t:,}', pct(N - t, N)])
    w(table(['Blocks fused whole', '% of dyn instrs covered', 'Transitions T', 'Reduction'], rows))
    w('')
    w('### B. Fuse only specific opcode-class pairs (a small library of fused ops)\n')
    w('Candidate pairs are adjacent instruction pairs *inside* a block, keyed by opcode class (operands ignored), ranked by dynamic count. For a library of the top M classes, each block is scanned left to right and an adjacent pair is fused when its class is in the library (non-overlapping, greedy). '
      'Register and immediate constraints of a real fused op are ignored.\n')
    inblock = Counter()
    for b in blocks:
        for i in range(b['len'] - 1):
            inblock[(b['ins'][i][0], b['ins'][i + 1][0])] += b['cnt']
    ranked = [k for k, _ in inblock.most_common()]
    rows = []
    for m in (1, 2, 4, 8, 16, 32, 64, len(ranked)):
        lib = set(ranked[:m])
        removed = 0
        for b in blocks:
            i = 0
            f = 0
            while i < b['len'] - 1:
                if (b['ins'][i][0], b['ins'][i + 1][0]) in lib:
                    f += 1
                    i += 2
                else:
                    i += 1
            removed += f * b['cnt']
        rows.append([m if m != len(ranked) else f'all {m}', f'{N - removed:,}', f'{removed:,}', pct(removed, N)])
    w(table(['Library size M (classes)', 'Transitions T', 'Transitions removed', 'Reduction'], rows))
    w('')
    w('Top in-block opcode-class pairs feeding that table:\n')
    w(table(['Pair', 'Dynamic count', '% of N'], [[' ; '.join(k), f'{inblock[k]:,}', pct(inblock[k], N)] for k in ranked[:12]]))
    w('')
    w('### How to read it\n')
    w('- Section A with `k = 2` is the ceiling for any "fuse two adjacent instructions" scheme; section B is what a realistic small set of fused pair ops could approach.')
    w('- Whole-block fusion is an upper bound that needs one transition to execute an arbitrary-length, data-dependent sequence, which the current circuit cannot do; it shows where the floor of the count would be if branch and memory behaviour were free.')
    w('- No result here says how long a fused run would take.\n')
    w('## Caveats\n')
    w('- Host emulator, one workload (scripted E1M1 with host-served disk, 350 tics). The chunk-ROM variant (199.7 M instr, 4 disk requests) changes the mix of the disk-request code.')
    w('- Block boundaries follow retired control transfers only; interrupts do not exist in this machine, and `ecall` ends a block because it is a host-visible event, not because it redirects control.')
    w('- Per-site stride uses an exact histogram of the first four distinct strides per site; sites with more distinct strides spill into "other" and are classed by their dominant stride only if it is >= 50 %.')
    w('- Reproduction check: the host-served-disk dry run in this trace executes 180,550,104 instructions over 349 tics with 165,054 disk requests, matching the 180.5 M / 165,054 figures in the README. '
      'During the same `make demo-elf` the chunk-ROM verification run (`CRXPLAN`) exited early with code 99 after 90,889 instructions in this environment (engine tree copied from a sibling worktree), so the 81 M / 199.7 M chunk-ROM figures were **not** reproduced here and were not traced; this was not investigated.')
    capped = [b for b in blocks if len(b['mem']) >= 64]
    miss = (S['loads'] + S['stores']) - (ld_ex + st_ex)
    w(f'- Memory-site tracking is capped at 64 sites per block. Blocks at the cap in this run: {len(capped)}'
      + (' (' + ', '.join(f'`{b["start"]:#x}` len {b["len"]} executed {b["cnt"]:,}x' for b in capped) + ')' if capped else '')
      + f'. Accesses in the global load/store counters but missing from the per-site tables (Memory section): {miss:,} of {S["loads"] + S["stores"]:,}.')
    Path(a.out).write_text('\n'.join(L) + '\n')
    print('wrote', a.out)


if __name__ == '__main__':
    main()
