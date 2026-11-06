#!/usr/bin/env python3
"""Chunk ROM: eliminate guest disk requests inside a run chunk by pre-filling the data ROM.

The guest (ports/doomdmc/qplat.c crx_read, built with -DQ_CHUNKROM) looks every disk read up in an
extent table at Q_CRX_BASE in the data ROM; a hit is a ROM copy (no mailbox request, no model pause).
The host builds that window per chunk from the exact disk ranges the chunk will read (a host dry run
with the C twin: rv32_fast REQLOG=file records (offset,len,ra,tic) per request) and writes it into the
snapshot's data ROM (fill_drom).

Window layout (u32 LE): [0] 'CRX1' [1] n  [2..130] guide (257 u16), then (disk offset, ROM address) i=0..n (entry n is the
end sentinel); then the blob. Every extent starts at a ROM address congruent to its disk offset mod 4
(padding bytes are real disk bytes appended to the previous extent) so word copies stay aligned.

Chunks are ranges of FRAME-MARKER counts (lo <= markers seen < hi): a window switch is only possible at a
model segment boundary, and a frame marker is the one place a segment can always end.
usage:
  chunkrom.py REQLOG DISK --tics C   (C = markers per chunk) [--budget B] [--out plan.bin]    fixed chunks of C tics
  chunkrom.py REQLOG DISK --greedy [--budget B] [--out plan.bin]    longest chunks that fit B bytes
plan.bin (for rv32_fast CRXPLAN=): records u32 start_tic,end_tic,nwords,words[]
"""
import argparse, struct, sys
import numpy as np

CRX_BASE = 0x28C00      # must match Q_CRX_BASE (qplat.c) / Q_CRX_BASE_LD (lowres.sh CHUNKROM=1)
DROM_BASE = 0x20000
DROM_END = 0x3F000      # 0x3f000.. holds the small-app rodata of the merged image
MAGIC = 0x31585243      # 'CRX1'
GUIDE_BYTES = 516       # 257 u16 guide entries (16 KB buckets over a 4 MB disk), padded to a word
GAP = 16                # merge extents closer than this (the hole is filled with real disk bytes)


def load_reqlog(path):
    a = np.fromfile(path, dtype='<u4').reshape(-1, 5)   # rv32_fast REQLOG: off, len, ra, tic, frame-marker count
    return a[:, 0].astype(np.int64), a[:, 1].astype(np.int64), a[:, 4].astype(np.int64)  # off, len, markers seen


def extents_of(off, ln, disk_len, gap=GAP):
    """Merged [start,end) disk extents covering all requests (holes <= gap bytes are bridged)."""
    if len(off) == 0:
        return []
    m = np.zeros(disk_len + 1, dtype=bool)
    # difference array over request intervals
    d = np.zeros(disk_len + 2, dtype=np.int32)
    np.add.at(d, off, 1)
    np.add.at(d, off + ln, -1)
    m = np.cumsum(d[:disk_len + 1]) > 0
    idx = np.flatnonzero(m)
    cut = np.flatnonzero(np.diff(idx) > gap + 1)
    st = np.concatenate(([0], cut + 1))
    en = np.concatenate((cut, [len(idx) - 1]))
    return [(int(idx[a]), int(idx[b]) + 1) for a, b in zip(st, en)]


def window_size_bound(ext):
    """Conservative window bytes for extents: header + table + blob + <=3 alignment bytes per extent."""
    return 8 + GUIDE_BYTES + 8 * (len(ext) + 1) + 3 + sum(e - s + 3 for s, e in ext)


def build_window(ext, disk, base=CRX_BASE, limit=DROM_END):
    """Bytes of the ROM window for extents [(start,end)...] (sorted, disjoint) cut from `disk`."""
    n = len(ext)
    pos = base + 8 + GUIDE_BYTES + 8 * (n + 1)
    ents, blob = [], bytearray()
    blob_base = pos
    for i, (s, e) in enumerate(ext):
        while (pos - s) & 3:                       # align the extent start; filler = bytes before s or zero
            blob.append(0); pos += 1               # (only possible for i == 0: later pads go into prev extent)
        ents.append((s, pos))
        chunk = bytes(disk[s:e])
        pos += len(chunk); blob += chunk
        if i + 1 < n:                              # pad this extent with real bytes so the next one is aligned
            nxt = ext[i + 1][0]
            pad = (nxt - pos) & 3
            assert e + pad <= nxt, 'extents too close for padding'
            blob += bytes(disk[e:e + pad]); pos += pad
    ents.append((0xFFFFFFFF, pos))
    if pos > limit:
        raise ValueError(f'chunk ROM window needs {pos - base} B, only {limit - base} available')
    starts = [o for o, _ in ents[:-1]] + [0xFFFFFFFF]
    import bisect
    guide = struct.pack('<258H', *[max(0, min(n, bisect.bisect_right(starts[:n], b << 14) - 1)) for b in range(257)], 0)
    assert len(guide) == GUIDE_BYTES
    hdr = struct.pack('<II', MAGIC, n) + guide + b''.join(struct.pack('<II', o, r) for o, r in ents)
    out = bytes(hdr) + bytes(blob)
    assert len(out) == pos - base
    return out


def fill_drom(machine, extents, disk, base=CRX_BASE):
    """Install the chunk's extents into a ref.Machine's data ROM (what the host does to a snapshot before
    the next Qwen turn). machine.drom is `bytes` (chipformer.rv.ref.Machine); core.snapshot() loads it
    (and rebuilds its DROM tables because hash(m.drom) changes). Reads are then ROM hits in the guest.
    extents: [(start,end)...] disk ranges; disk: the block-device image. Returns the window length."""
    win = build_window(extents, disk, base)
    off = base - DROM_BASE
    d = bytearray(machine.drom.ljust(DROM_END - DROM_BASE, b'\0'))
    d[off:DROM_END - DROM_BASE] = bytes(DROM_END - base)       # zero the whole window first
    d[off:off + len(win)] = win
    machine.drom = bytes(d)
    return len(win)


def clear_drom(machine, base=CRX_BASE):
    d = bytearray(machine.drom)
    for i in range(base - DROM_BASE, min(len(d), base - DROM_BASE + 8)):
        d[i] = 0
    machine.drom = bytes(d)


def plan_fixed(off, ln, tic, disk_len, C):
    out = []
    for lo in range(0, int(tic.max()) + 1, C):
        sel = (tic >= lo) & (tic < lo + C)
        out.append((lo, lo + C, extents_of(off[sel], ln[sel], disk_len)))
    return out


def plan_greedy(off, ln, tic, disk_len, budget):
    """Longest chunks whose window fits `budget` bytes (a tic that alone exceeds it is an error)."""
    nt = int(tic.max()) + 1
    order = np.argsort(tic, kind='stable')
    off, ln, tic = off[order], ln[order], tic[order]
    bounds = np.searchsorted(tic, np.arange(nt + 1))
    out, lo = [], 0
    while lo < nt:
        hi = lo + 1
        best = extents_of(off[bounds[lo]:bounds[hi]], ln[bounds[lo]:bounds[hi]], disk_len)
        if window_size_bound(best) > budget:
            raise ValueError(f'tic {lo} alone needs {window_size_bound(best)} B > budget {budget}')
        while hi < nt:
            cand = extents_of(off[bounds[lo]:bounds[hi + 1]], ln[bounds[lo]:bounds[hi + 1]], disk_len)
            if window_size_bound(cand) > budget:
                break
            best, hi = cand, hi + 1
        out.append((lo, hi, best)); lo = hi
    return out


def write_plan(path, plan, disk):
    with open(path, 'wb') as f:
        for lo, hi, ext in plan:
            w = build_window(ext, disk)
            w += bytes(-len(w) % 4)
            f.write(struct.pack('<III', lo, hi, len(w) // 4) + w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('reqlog'); ap.add_argument('disk')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--tics', type=int); g.add_argument('--greedy', action='store_true')
    ap.add_argument('--budget', type=int, default=DROM_END - CRX_BASE)
    ap.add_argument('--out', help='binary plan for rv32_fast CRXPLAN')
    ap.add_argument('--json', help='JSON plan for model_doom_qwen.py --rom-plan')
    a = ap.parse_args()
    disk = open(a.disk, 'rb').read()
    off, ln, tic = load_reqlog(a.reqlog)
    plan = plan_greedy(off, ln, tic, len(disk), a.budget) if a.greedy else plan_fixed(off, ln, tic, len(disk), a.tics)
    for lo, hi, ext in plan:
        sel = (tic >= lo) & (tic < hi)
        w = len(build_window(ext, disk, limit=1 << 30))
        print(f'chunk markers {lo:3d}-{hi:3d}: reqs {int(sel.sum()):6d} reqB {int(ln[sel].sum()):8d} '
              f'extents {len(ext):4d} blob {sum(e - s for s, e in ext):7d} window {w:7d} '
              f'{"OK" if w <= a.budget else "OVER"}')
    print('chunks', len(plan))
    if a.out:
        write_plan(a.out, plan, disk)
    if a.json:
        import json
        json.dump(dict(base=CRX_BASE, chunks=[dict(lo=lo, hi=hi, extents=ext) for lo, hi, ext in plan]),
                  open(a.json, 'w'))


if __name__ == '__main__':
    main()
