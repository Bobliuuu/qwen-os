"""Real doomd ELF on Qwenputer's official reference machine vs the fast C twin; the model-run
plan (tools/model_doom_qwen.py --dry-run).  Skipped unless upstream (PYTHONPATH), the DMC100 disk
image (DOOMDMC_DISK or the default path), build/qwenos-doomdmc.elf and build/rv32_fast exist."""
import os, subprocess, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DISK = Path(os.environ.get('DOOMDMC_DISK', '../engine/DMC100-Doom/build/sw/nor/E1.img'))
ELF, FAST = ROOT / 'build/qwenos-doomdmc.elf', ROOT / 'build/rv32_fast'

def have_upstream():
    try:
        import chipformer.rv.ref  # noqa
        return True
    except ImportError:
        return False

@unittest.skipUnless(have_upstream() and DISK.is_file() and ELF.is_file() and FAST.is_file(),
                     'needs upstream on PYTHONPATH, E1.img, doomdmc elf and build/rv32_fast')
class UpstreamDoomd(unittest.TestCase):
    def run_tool(self, *a):
        return subprocess.run([sys.executable, str(ROOT / 'tools' / a[0])] + list(a[1:]),
                              capture_output=True, text=True, timeout=600)

    def test_ref_matches_fast_twin(self):
        r = self.run_tool('upstream_doomd.py', str(ELF), str(DISK), '--max-instructions', '1700000',
                          '--compare-fast', str(FAST))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('marker steps equal : True', r.stdout)
        self.assertIn('console bytes equal: True', r.stdout)
        self.assertIn('final RAM equal    : True', r.stdout)

    def test_model_run_plan_title_frame(self):
        r = self.run_tool('model_doom_qwen.py', '--elf', str(ELF), '--disk', str(DISK), '--dry-run',
                          '--snapshot-marker', '5', '--out', os.devnull)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('"frame_markers_in_output": 1', r.stdout)

if __name__ == '__main__':
    unittest.main()
