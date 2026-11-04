"""Determinism and reference-vs-C-twin lockstep of the real doomd ELF (build/regress/prod1.elf,
made by tools/doomd_regress.sh; override with DOOMD_ELF).  Skipped when the ELF, the NOR image
(DOOMDMC_DISK) or build/rv32_fast is missing.

  * determinism: the same ELF run twice on the C twin gives byte-identical console output,
    register file and RAM image
  * lockstep (LOCKSTEP_INSTR, default 2,500,000 instructions, three checkpoints): the independent
    Python reference (tools/rv32_qwenputer.py + wad_device.py) and, when upstream is on PYTHONPATH,
    Qwenputer's official reference machine agree with the C twin on console bytes, final RAM,
    and (Python reference) pc + all registers
"""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
ELF = Path(os.environ.get('DOOMD_ELF', ROOT / 'build/regress/prod1.elf'))
DISK = Path(os.environ.get('DOOMDMC_DISK', str(ROOT.parent/'engine/DMC100-Doom/build/sw/nor/E1.img')))
FAST = ROOT / 'build/rv32_fast'
N = int(os.environ.get('LOCKSTEP_INSTR', '2500000'))
KBOX, DBOX = 0x154, 0x15c   # qos_input_mailbox, qos_disk_mailbox of build/kernel-doomd.elf


def twin(elf, n, tmp, tag):
    out, regs = Path(tmp) / f'{tag}.bin', Path(tmp) / f'{tag}.regs'
    env = dict(os.environ, REGDUMP=str(regs))
    subprocess.run([str(FAST), str(elf), str(DISK), '%x' % KBOX, '%x' % DBOX, str(out), str(n)],
                   env=env, capture_output=True, timeout=600)
    return out.read_bytes(), Path(str(out) + '.ram').read_bytes(), regs.read_text()


@unittest.skipUnless(ELF.is_file() and DISK.is_file() and FAST.is_file(),
                     'needs build/regress/prod1.elf (tools/doomd_regress.sh), E1.img and build/rv32_fast')
class DoomdDeterminism(unittest.TestCase):
    def test_same_elf_twice_is_identical(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = twin(ELF, 3_000_000, t, 'a'), twin(ELF, 3_000_000, t, 'b')
        self.assertTrue(a[0], 'no console output')
        self.assertEqual(a[0], b[0], 'console bytes differ between two runs of the same ELF')
        self.assertEqual(a[1], b[1], 'RAM image differs between two runs of the same ELF')
        self.assertEqual(a[2], b[2], 'registers differ between two runs of the same ELF')

    def test_game_state_hash_stream_is_deterministic(self):
        chk = ROOT / 'build/regress/chk2.elf'
        if not chk.is_file():
            self.skipTest('needs build/regress/chk2.elf')
        with tempfile.TemporaryDirectory() as t:
            a, b = twin(chk, 700_000_000, t, 'a'), twin(chk, 700_000_000, t, 'b')
        self.assertIn(b'TICHASH', a[0])
        self.assertEqual(a[0], b[0])


@unittest.skipUnless(ELF.is_file() and DISK.is_file() and FAST.is_file(),
                     'needs build/regress/prod1.elf (tools/doomd_regress.sh), E1.img and build/rv32_fast')
class PyRefLockstep(unittest.TestCase):
    def test_python_reference_matches_twin_at_checkpoints(self):
        from rv32_qwenputer import CPU
        from wad_device import WadDevice
        cpu = CPU(str(ELF))
        cpu.sym['qos_disk_mailbox'] = DBOX
        dev = WadDevice(cpu, DISK.read_bytes())
        marks = [N // 5, N // 2, N]
        with tempfile.TemporaryDirectory() as t:
            for m in marks:
                while cpu.steps < m:
                    cpu.step()
                    dev.tick()
                out, ram, regs = twin(ELF, m, t, f'c{m}')
                py_out = bytes(b & 255 for b in cpu.byte_events if b < 256)
                self.assertEqual(py_out, out, f'console bytes differ within the first {m} instructions')
                self.assertEqual(bytes(cpu.mem[:0x8000]), ram, f'RAM differs after {m} instructions')
                lines = regs.split('\n')
                self.assertEqual(lines[0], f'pc {cpu.pc:08x} steps {m}', f'pc differs after {m} instructions')
                for i in range(1, 32):
                    self.assertEqual(lines[i + 1], f'x{i} {cpu.reg[i]:08x}', f'x{i} differs after {m} instructions')

    def test_twin_step_budget_is_exact(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertTrue(twin(ELF, 12345, t, 'x')[2].startswith('pc '))
            self.assertIn('steps 12345', twin(ELF, 12345, t, 'y')[2].split('\n')[0])


def have_upstream():
    try:
        import chipformer.rv.ref  # noqa
        return True
    except ImportError:
        return False


@unittest.skipUnless(have_upstream() and ELF.is_file() and DISK.is_file() and FAST.is_file(),
                     'needs upstream Qwenputer on PYTHONPATH, prod1.elf, E1.img, build/rv32_fast')
class UpstreamLockstep(unittest.TestCase):
    def test_official_reference_matches_twin(self):
        r = subprocess.run([sys.executable, str(ROOT / 'tools/upstream_doomd.py'), str(ELF), str(DISK),
                            '--kernel-elf', str(ROOT / 'build/kernel-doomd.elf'), '--max-instructions', str(N),
                            '--compare-fast', str(FAST)],
                           capture_output=True, text=True, timeout=1800)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertIn('console bytes equal: True', r.stdout)
        self.assertIn('final RAM equal    : True', r.stdout)


if __name__ == '__main__':
    unittest.main()
