"""Unit tests of tools/model_doom_qwen.py (chunk planner, segment logic, --dry-run) on a tiny
synthetic RV32 program, so they run in about a second and do not depend on the DOOM build.
The tool is read-only here (another agent extends it): only its stable surface is used
(plan, Truth, clone, breakpoint_at, oracle_run, symbols, main/--dry-run).  Skipped unless the
upstream Qwenputer reference (chipformer.rv.ref) is on PYTHONPATH.

Guest program (disk mailbox at 0x100): 4 x { publish a disk request, wait for the reply,
putc(0x02) frame marker }, then exit(0).
"""
import contextlib, io, json, os, struct, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

try:
    import chipformer.rv.ref  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


def i_(op, rd, f3, rs1, imm): return (imm & 0xfff) << 20 | rs1 << 15 | f3 << 12 | rd << 7 | op
def s_(f3, rs1, rs2, imm): return (imm >> 5 & 0x7f) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | (imm & 31) << 7 | 0x23
def b_(f3, rs1, rs2, off):
    return ((off >> 12 & 1) << 31 | (off >> 5 & 63) << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 |
            (off >> 1 & 15) << 8 | (off >> 11 & 1) << 7 | 0x63)
def addi(rd, rs, imm): return i_(0x13, rd, 0, rs, imm)
def lw(rd, rs, imm): return i_(0x03, rd, 2, rs, imm)
def sw(rs2, rs1, imm): return s_(2, rs1, rs2, imm)
ECALL = 0x73
S0, S1, T0, T1, T2, A0, A7 = 8, 9, 5, 6, 7, 10, 17
MARKERS, DBOX, KBOX = 4, 0x100, 0x80


def program():
    p = [addi(S0, 0, DBOX), addi(S1, 0, 0),
         addi(S1, S1, 1), addi(T0, 0, 16), sw(T0, S0, 4), addi(T0, 0, 4), sw(T0, S0, 8),
         sw(S1, S0, 0),                       # 7: the store that publishes the request
         lw(T1, S0, 12), b_(1, T1, S1, -4),   # wait for the device's release word
         addi(A7, 0, 1), addi(A0, 0, 2), ECALL,
         addi(T2, 0, MARKERS), b_(4, S1, T2, -48),
         addi(A7, 0, 93), addi(A0, 0, 0), ECALL]
    return b''.join(struct.pack('<I', w) for w in p)


def write_elf(path, code, base=0x40000):
    ehdr = b'\x7fELF\x01\x01\x01' + bytes(9) + struct.pack('<HHIIIIIHHHHHH', 2, 243, 1, base, 52, 0, 0, 52, 32, 1, 0, 0, 0)
    phdr = struct.pack('<8I', 1, 84, base, base, len(code), len(code), 5, 4)
    Path(path).write_bytes(ehdr + phdr + code)


@unittest.skipUnless(HAVE, 'needs qwenputer/experimental/riscv on PYTHONPATH')
class ModelPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import model_doom_qwen as M
        cls.M = M
        cls.tmp = tempfile.TemporaryDirectory()
        cls.elf = os.path.join(cls.tmp.name, 'tiny.elf')
        write_elf(cls.elf, program())
        cls.disk = os.path.join(cls.tmp.name, 'disk.img')
        Path(cls.disk).write_bytes(bytes(range(256)) * 4)
        cls._sym = M.symbols
        M.symbols = lambda k: {'qos_input_mailbox': KBOX, 'qos_disk_mailbox': DBOX}   # no kernel ELF needed
        import upstream_ref
        cls._usym = upstream_ref.symbols

    @classmethod
    def tearDownClass(cls):
        cls.M.symbols = cls._sym
        cls.tmp.cleanup()

    def truth(self, keys=(), pause=True):
        return self.M.Truth(self.elf, Path(self.disk).read_bytes(), 'unused', list(keys), pause)

    def args(self, **kw):
        a = dict(snapshot_marker=1, frames=2, max_instructions=0)
        a.update(kw)
        return type('A', (), a)()

    def segments(self, **kw):
        return list(self.M.plan(self.truth(), self.args(**kw)))

    def test_segments_end_at_disk_requests_and_at_the_last_marker(self):
        # frames=2 after the snapshot at marker 1: requests 2 and 3 stop a segment each (marker 2 is
        # inside the second one), marker 3 ends the run
        segs = self.segments()
        self.assertEqual([s['reason'] for s in segs], ['disk', 'disk', 'marker'])
        self.assertEqual([s['index'] for s in segs], [1, 2, 3])
        self.assertEqual([s['out'] for s in segs], [b'', b'\x02', b'\x02'])

    def test_segments_are_contiguous_and_stop_on_ebreak(self):
        segs = self.segments()
        for a, b in zip(segs, segs[1:]):
            # a disk stop sits BEFORE the request store, which the host then executes (+1)
            self.assertEqual(b['start_steps'], a['start_steps'] + a['instr'] + (1 if a['reason'] == 'disk' else 0))
        for s in segs:
            word = s['start'].rom[(s['stop_pc'] - 0x40000) >> 2]
            self.assertEqual(word, self.M.EBREAK)
            self.assertGreaterEqual(s['tokens'], s['instr'])     # >= 1 chip token per instruction

    def test_disk_stop_is_the_request_store(self):
        segs = self.segments()
        store_pc = 0x40000 + 4 * 7
        self.assertEqual([s['stop_pc'] for s in segs if s['reason'] == 'disk'], [store_pc, store_pc])

    def test_marker_segment_ends_on_a_fresh_pc_after_the_marker(self):
        last = self.segments()[-1]
        self.assertEqual(last['reason'], 'marker')
        self.assertEqual(last['out'], b'\x02')
        self.assertGreater(last['stop_pc'], 0x40000 + 4 * 12)   # past the putc ecall

    def test_dry_run_oracle_matches_every_segment(self):
        for s in self.segments():
            i, t, out = self.M.oracle_run(self.M.clone(s['start']))
            self.assertEqual(i, s['instr'] + 1)              # the ebreak pair
            self.assertEqual(out, s['out'])

    def test_plan_is_deterministic(self):
        key = lambda segs: [(s['reason'], s['start_steps'], s['stop_pc'], s['instr'], s['tokens'], s['out']) for s in segs]
        self.assertEqual(key(self.segments()), key(self.segments()))

    def test_no_disk_pause_makes_one_marker_segment_per_frame(self):
        segs = list(self.M.plan(self.truth(pause=False), self.args()))
        self.assertEqual([s['reason'] for s in segs], ['marker'])
        # the walk to a fresh pc may run past more markers in a loop this tight (here all pcs repeat)
        self.assertGreaterEqual(segs[0]['out'].count(2), 2)

    def test_clone_is_independent(self):
        t = self.truth()
        c = self.M.clone(t.m)
        c.record()
        self.assertEqual(t.m.steps + 1, c.steps)
        self.assertNotEqual(t.m.pc, c.pc)

    # XFAIL (merge): needs the keys-inside-segment check of the updated tools/model_doom_qwen.py, which is owned by another
    # agent and was deliberately NOT replaced in this tree (the stock bundle version does not raise here).
    @unittest.expectedFailure
    def test_key_inside_a_segment_is_refused(self):
        t = self.truth(keys=[('p', 3)])
        with self.assertRaises(RuntimeError):
            list(self.M.plan(t, self.args()))

    def test_max_instructions_cap(self):
        with self.assertRaises(RuntimeError):
            list(self.M.plan(self.truth(), self.args(max_instructions=3)))

    def test_markerparser_ignores_dump_payload(self):
        from upstream_doomd import MarkerParser
        p = MarkerParser()
        pkt = b'\x01P\x05' + b'\x01W' + bytes(10) + b'\x01D' + struct.pack('<H', 6) + bytes([2, 2, 2, 1, 2, 2]) + b'\x01E\x07\x00'
        self.assertEqual(sum(p.feed(c) for c in pkt), 0)
        self.assertTrue(p.feed(2))

    def run_main(self, *argv):
        out = io.StringIO()
        old = sys.argv
        sys.argv = ['model_doom_qwen.py', *argv]
        try:
            with contextlib.redirect_stdout(out):
                self.M.main()
        finally:
            sys.argv = old
        return out.getvalue()

    def test_cli_dry_run_report(self):
        txt = self.run_main('--elf', self.elf, '--disk', self.disk, '--kernel-elf', 'unused', '--dry-run',
                            '--snapshot-marker', '1', '--frames', '2', '--out', os.devnull)
        rep = json.loads(txt[txt.index('{'):])
        self.assertEqual(rep['segments'], 3)
        self.assertEqual(rep['frame_markers_in_output'], 2)
        self.assertIn('dry-run', rep['mode'])
        self.assertEqual(rep['console_bytes'], 2)
        self.assertGreaterEqual(rep['planned_chip_tokens'], rep['instructions'])

    def test_cli_rejects_missing_model_and_bad_dump(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as c:
                self.run_main('--elf', self.elf, '--disk', self.disk)       # no model, no --dry-run
            self.assertEqual(c.exception.code, 2)
            with self.assertRaises(SystemExit) as c:
                self.run_main('--elf', self.elf, '--disk', self.disk, '--dry-run', '--dump', '--snapshot-marker', '0')
            self.assertEqual(c.exception.code, 2)

    def test_cli_max_segments(self):
        with self.assertRaises(SystemExit):
            self.run_main('--elf', self.elf, '--disk', self.disk, '--kernel-elf', 'unused', '--dry-run',
                          '--snapshot-marker', '1', '--frames', '2', '--max-segments', '2', '--out', os.devnull)


if __name__ == '__main__':
    unittest.main()
