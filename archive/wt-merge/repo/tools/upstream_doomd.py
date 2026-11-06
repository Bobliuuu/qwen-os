#!/usr/bin/env python3
"""Run the real /bin/doomd image (build/qwenos-doomdmc.elf) on Qwenputer's OFFICIAL reference
machine (chipformer.rv.ref.Machine: pre-decoded ROM, DROM, 32 KB word RAM, traced records) and
compare against the fast C twin (tools/rv32_fast.c).  NOT a model run.

 PYTHONPATH=<qwenputer>/experimental/riscv python3 tools/upstream_doomd.py \
     build/qwenos-doomdmc.elf E1.img --max-instructions 12000000 --key p@0 \
     --out run.bin [--compare-fast build/rv32_fast]

The disk device only copies requested bytes into the guest mailbox (host = dumb storage).
Frame marker = console byte 0x02 outside dump packets (same parser as rv32_fast.c).
Key 'c@N' is written to the guest input mailbox once N markers have been seen.
--compare-fast runs rv32_fast for the same instruction budget and diffs: marker steps,
console byte stream, and the final 32 KB RAM image.
"""
import argparse, subprocess, sys, tempfile, time, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from upstream_ref import symbols, ReferenceDiskDevice


class MarkerParser:
    """Dump-packet aware 0x02 detector (mirror of rv32_fast.c)."""
    def __init__(self):
        self.ps = self.pskip = self.plen = self.pn = 0

    def feed(self, c):
        mark = False
        if self.pskip > 0:
            self.pskip -= 1
        elif self.ps == 0:
            if c == 1: self.ps = 1
            elif c == 2: mark = True
        elif self.ps == 1:
            self.ps = 0
            if c == ord('D'): self.ps = 2; self.pn = 0; self.plen = 0
            elif c == ord('W'): self.pskip = 10
            elif c == ord('P'): self.pskip = 1
            elif c == ord('E'): self.pskip = 2
        elif self.ps == 2:
            self.plen |= c << (8 * self.pn); self.pn += 1
            if self.pn == 2: self.ps = 0; self.pskip = self.plen
        return mark


def run_upstream(elf, disk, max_instr, keys, kbox, dbox, stop_frames=None, progress=True):
    from chipformer.rv import elf as relf, ref
    m = ref.Machine.from_program(relf.program(elf))
    dev = ReferenceDiskDevice(m, dbox, disk)
    par = MarkerParser(); seen = 0; marks = []; kseq = 0
    pend = [[c, int(n), False] for c, n in keys]
    t0 = time.time(); records = 0; toks = 1; nxt = 1000000
    while not m.halted and m.steps < max_instr:
        t = m.record(); records += 1; toks += len(t)
        if m.fault: break
        dev.tick()
        if len(m.out) != seen:
            for c in m.out[seen:]:
                if par.feed(c):
                    marks.append(m.steps - 1)  # rv32_fast logs steps before the ecall retires
                    for k in pend:
                        if not k[2] and len(marks) >= k[1]:
                            k[2] = True
                            sh = 8 * (kseq & 3); w = m.ram[(kbox + 4) // 4]
                            m.ram[(kbox + 4) // 4] = (w & ~(255 << sh)) | (ord(k[0]) << sh); kseq += 1; m.ram[kbox // 4] = kseq
                            break
            seen = len(m.out)
        if progress and m.steps >= nxt:
            print(f'  ..{m.steps} instr {time.time()-t0:.0f}s', file=sys.stderr); nxt += 1000000
        if stop_frames and len(marks) >= stop_frames: break
    return m, marks, records, toks, dev, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('elf'); ap.add_argument('disk')
    ap.add_argument('--kernel-elf', default=None)
    ap.add_argument('--max-instructions', type=int, default=12_000_000)
    ap.add_argument('--key', action='append', default=[], help='c@N')
    ap.add_argument('--out', default=None)
    ap.add_argument('--stop-frames', type=int, default=None)
    ap.add_argument('--compare-fast', default=None, help='path to built tools/rv32_fast')
    a = ap.parse_args()
    sys.path[:0] = [p for p in [os.environ.get('PYTHONPATH')] if p]
    try:
        import chipformer.rv.ref  # noqa
    except ImportError as e:
        sys.exit('set PYTHONPATH to qwenputer/experimental/riscv: ' + str(e))
    kelf = a.kernel_elf or str(Path(a.elf).with_name('kernel-doomd.elf'))
    sy = symbols(kelf); kbox, dbox = sy['qos_input_mailbox'], sy['qos_disk_mailbox']
    keys = [(k[0], k.split('@')[1]) for k in a.key]
    disk = Path(a.disk).read_bytes()
    m, marks, records, toks, dev, dt = run_upstream(a.elf, disk, a.max_instructions, keys, kbox, dbox, a.stop_frames)
    print(f'upstream: steps={m.steps} records={records} tokens={toks} tok/instr={toks/max(m.steps,1):.4f} '
          f'halted={m.halted} exit={m.exit_code} fault={m.fault} frames={len(marks)} disk_reads={len(dev.reads)} {dt:.0f}s')
    print('upstream marker steps (first 8):', marks[:8])
    if a.out: Path(a.out).write_bytes(bytes(m.out))
    rc = 0
    if m.fault: rc = 1
    if a.compare_fast:
        tmp = tempfile.mkdtemp(prefix='updoomd'); fo = os.path.join(tmp, 'fast.bin')
        r = subprocess.run([a.compare_fast, a.elf, a.disk, '%x' % kbox, '%x' % dbox, fo, str(m.steps)] + a.key,
                           capture_output=True, text=True)
        fmarks = [int(l.split(' at ')[1].split()[0]) for l in r.stderr.splitlines() if l.startswith('frame ')]
        fout = Path(fo).read_bytes(); fram = Path(fo + '.ram').read_bytes()
        uram = b''.join(w.to_bytes(4, 'little') for w in m.ram)
        print('fast steps line:', next((l for l in r.stderr.splitlines() if l.startswith('steps=')), r.stderr[:200]))
        print('marker steps equal :', fmarks == marks, '(fast', len(fmarks), 'upstream', len(marks), ')')
        print('console bytes equal:', fout == bytes(m.out), len(fout), len(m.out))
        print('final RAM equal    :', fram == uram)
        if not (fmarks == marks and fout == bytes(m.out) and fram == uram): rc = 4
        for f in (fo, fo + '.ram'): os.path.exists(f) and os.remove(f)
        os.rmdir(tmp)
    sys.exit(rc)

if __name__ == '__main__': main()
