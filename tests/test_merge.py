import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from merge_elf import parse,merge

class MergeTests(unittest.TestCase):
    def test_all_programs_have_correct_entry_and_segments(self):
        for name,address in [('kernel',0x40000),('shell',0x60000),('paint',0x68000),('raycast',0x70000),('asset',0x78000),('doom',0x7c000)]:
            ent,segs=parse((ROOT/'build'/f'{name}.elf').read_bytes())
            self.assertEqual(ent,address)
            self.assertTrue(any(v<=address<v+len(d) and f&1 for v,d,f in segs))

    def test_combined_image_contains_all_six_executables(self):
        ent,segs=parse((ROOT/'build/qwenos.elf').read_bytes())
        self.assertEqual(ent,0x40000)
        self.assertTrue(all(any(v<=a<v+len(d) and f&1 for v,d,f in segs) for a in [0x40000,0x60000,0x68000,0x70000,0x78000,0x7c000]))

    def test_doom_writable_sections_occupy_guest_ram(self):
        entry,segments=parse((ROOT/'build/doom.elf').read_bytes())
        writes=[(va,len(blob)) for va,blob,flags in segments if flags & 2]
        self.assertTrue(writes)
        self.assertTrue(all(0x1800<=a and a+n<=0x7000 for a,n in writes))
        kent,ksegments=parse((ROOT/'build/kernel.elf').read_bytes())
        kernel_ram=[(va,len(blob)) for va,blob,flags in ksegments if flags & 2]
        self.assertTrue(all(a+n<=0x1800 for a,n in kernel_ram))

    def test_bad_elf_rejected(self):
        with self.assertRaises(ValueError):parse(b'not ELF')
        bad=bytearray((ROOT/'build/shell.elf').read_bytes())
        bad[18:20]=b'\x00\x00'
        with self.assertRaises(ValueError):parse(bad)

    def test_overlapping_apps_rejected(self):
        # Same shell linked twice must not overlap silently.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                merge(str(Path(td)/'out.elf'),[str(ROOT/'build/kernel.elf'),str(ROOT/'build/shell.elf'),str(ROOT/'build/shell.elf'),str(ROOT/'build/raycast.elf')])

if __name__=='__main__':unittest.main()
