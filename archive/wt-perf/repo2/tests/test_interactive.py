"""Input-driven multi-frame rendering in the guest, verified at RAM boundary."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from interactive_frames import play

class InteractiveTests(unittest.TestCase):
    def test_multiple_guest_frames_are_generated(self):
        cpu,dev,frames=play(str(ROOT/'build/qwenos.elf'),'wd')
        self.assertEqual(cpu.exitcode,0)
        self.assertEqual(len(frames),3)
        self.assertGreater(len(dev.reads),20)
        self.assertNotEqual(frames[0],frames[1])
        self.assertNotEqual(frames[1],frames[2])
        self.assertEqual({len(x) for x in frames},{32*24})
