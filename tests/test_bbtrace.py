"""bbtrace (tools/bbtrace, rv32_fast -DBBTRACE) must be a pure observer: same instruction count, same console/output
bytes, same final registers and same final RAM as the plain rv32_fast, and its own block accounting must add up.
Host emulator only.

Case 1 (no game data): the kernel+apps image boots to the shell prompt and idles (a few hundred instructions).
Case 2 (needs the E1M1 demo image and the E1 NOR image, skipped otherwise): first 3,000,000 instructions of
build/demo/qwenos-e1m1.elf with the host-served disk (E1 image: $IMG or $DMC/build/sw/nor/E1.img)."""
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAST = ROOT / 'build/rv32_fast'
BB = ROOT / 'build/bbtrace'
SRC = ROOT / 'tools/rv32_fast.c'


def sym(elf, name):
    out = subprocess.run(['readelf', '-sW', str(elf)], capture_output=True, text=True, check=True).stdout
    for ln in out.splitlines():
        f = ln.split()
        if len(f) >= 8 and f[7] == name:
            return f[1].lstrip('0') or '0'
    raise KeyError(name)


def h(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(binary, elf, disk, maxi, td, tag, env_extra=None):
    kb, db = sym(ROOT / 'build/kernel-doomd.elf', 'qos_input_mailbox'), sym(ROOT / 'build/kernel-doomd.elf', 'qos_disk_mailbox')
    out = Path(td) / f'{tag}.bin'
    regs = Path(td) / f'{tag}.regs'
    env = dict(os.environ, REGDUMP=str(regs), BBOUT=str(Path(td) / f'{tag}.bb'))
    env.update(env_extra or {})
    p = subprocess.run([str(binary), str(elf), str(disk), kb, db, str(out), str(maxi)], env=env, capture_output=True, text=True)
    steps = [ln for ln in p.stderr.splitlines() if ln.startswith('steps=')]
    assert steps, p.stderr[-2000:]
    return {'steps_line': steps[0], 'out': h(out), 'ram': h(str(out) + '.ram'), 'regs': h(regs)}, Path(td) / f'{tag}.bb'


def summary(d):
    return {k: int(v) for k, v in (ln.split('\t') for ln in (d / 'summary.txt').read_text().splitlines())}


class BBTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FAST.parent.mkdir(exist_ok=True)
        subprocess.run(['cc', '-O2', '-o', str(FAST), str(SRC)], check=True)   # plain emulator, rebuilt from the same source
        subprocess.run(['cc', '-O2', '-DBBTRACE', '-I', str(ROOT / 'tools'), '-o', str(BB), str(SRC)], check=True)

    def check_equal(self, elf, disk, maxi):
        with tempfile.TemporaryDirectory() as td:
            plain, _ = run(FAST, elf, disk, maxi, td, 'plain')
            traced, bbdir = run(BB, elf, disk, maxi, td, 'traced')
            self.assertEqual(plain, traced)          # instruction count line, console bytes, final regs and RAM identical
            s = summary(bbdir)
            n = int(plain['steps_line'].split()[0].split('=')[1])
            self.assertEqual(s['steps'], n)
            self.assertEqual(s['block_instrs_plus_tail'], n)   # every executed instruction is in exactly one block (or the open tail)
            rows = [ln.split('\t') for ln in (bbdir / 'blocks.tsv').read_text().splitlines()]
            self.assertEqual(sum(int(r[1]) * int(r[2]) for r in rows), s['block_instrs'])
            self.assertEqual(sum(int(r[2]) for r in rows), s['dyn_blocks'])
            for r in rows:                                 # successor counts add up to the block count
                self.assertEqual(int(r[4]), int(r[2]))
            pairs = sum(int(ln.split('\t')[2]) for ln in (bbdir / 'pairs.tsv').read_text().splitlines())
            self.assertEqual(pairs, n - 1)                 # n instrs -> n-1 consecutive pairs
            trip = sum(int(ln.split('\t')[3]) for ln in (bbdir / 'triples.tsv').read_text().splitlines())
            self.assertEqual(trip, n - 2)
            return n

    def test_kernel_boot_to_idle(self):
        elf = ROOT / 'build/qwenos.elf'
        if not elf.exists() or not (ROOT / 'build/kernel-doomd.elf').exists():
            self.skipTest('build/qwenos.elf and build/kernel-doomd.elf needed (make all; make demo-elf)')
        with tempfile.NamedTemporaryFile() as z:
            z.write(b'\0' * 4096)
            z.flush()
            n = self.check_equal(elf, z.name, 1000000)
        self.assertGreater(n, 50)

    def test_e1m1_demo_prefix(self):
        elf = ROOT / 'build/demo/qwenos-e1m1.elf'
        dmc = os.environ.get('DMC', str(ROOT / '../engine/DMC100-Doom'))
        img = Path(os.environ.get('IMG', dmc + '/build/sw/nor/E1.img'))
        if not elf.exists() or not img.exists() or not (ROOT / 'build/kernel-doomd.elf').exists():
            self.skipTest('build/demo/qwenos-e1m1.elf (make demo-elf) and the E1 NOR image needed')
        n = self.check_equal(elf, img, 3000000)
        self.assertEqual(n, 3000000)


if __name__ == '__main__':
    unittest.main()
