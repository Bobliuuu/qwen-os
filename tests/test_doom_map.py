"""End-to-end guest DOOM-format map reader/render tests.

These assert actual RV32 guest execution, not Python rendering. They are not
full DOOM engine tests: textures, sector heights, BSP and monsters are absent.
"""
import struct
import sys
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from wad_device import doom_fixture, WadDevice, DEMO_DIRECTORY_OFFSET
from rv32_qwenputer import CPU


def symbols():
    out=subprocess.check_output(['readelf','-sW',str(ROOT/'build/kernel.elf')],text=True)
    return {line.split()[-1]:int(line.split()[1],16) for line in out.splitlines()
            if len(line.split())>=8 and line.split()[0].rstrip(':').isdigit()}


def boot_with_data(data, key=None):
    cpu=CPU(str(ROOT/'build/qwenos.elf'))
    dev=WadDevice(cpu,data)
    inject_addr=symbols()['qos_input_mailbox']
    injected=False
    for _ in range(500000):
        if cpu.halted:break
        cpu.step()
        dev.tick()
        if key and not injected and '$ run /bin/doom\n' in ''.join(cpu.output):
            cpu.store(inject_addr+4,4,ord(key))
            cpu.store(inject_addr,4,7)
            injected=True
    return cpu,dev,''.join(cpu.output)

class DoomMapTests(unittest.TestCase):
    def test_guest_parses_doom_map_and_renders_pixels(self):
        cpu,dev,log=boot_with_data(doom_fixture())
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: WAD map geometry rendered',log)
        self.assertIn('QWENOS_BOOT_OK',log)
        self.assertTrue(any(o==0x210300 and n==4 for o,n,ok in dev.reads))
        self.assertTrue(any(o==0x210200 and n==14 for o,n,ok in dev.reads))
        fb=symbols()['framebuffer']
        values=set(cpu.mem[fb:fb+768])
        self.assertTrue(10 in values or 11 in values or 12 in values)
        self.assertGreater(len(values),3)
    def test_key_changes_guest_wall_projection(self):
        base,_,out1=boot_with_data(doom_fixture())
        rotated,_,out2=boot_with_data(doom_fixture(),key='d')
        self.assertEqual(base.exitcode,0)
        self.assertEqual(rotated.exitcode,0)
        self.assertIn('doom: WAD map geometry rendered',out2)
        fb=symbols()['framebuffer']
        self.assertNotEqual(base.mem[fb:fb+768],rotated.mem[fb:fb+768])
    def test_malformed_linedef_rejected_by_guest(self):
        data=bytearray(doom_fixture())
        struct.pack_into('<H',data,0x210200,65000)
        cpu,dev,log=boot_with_data(bytes(data))
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: no valid E1M1/MAP01 WAD map',log)
        self.assertNotIn('doom: WAD map geometry rendered',log)
    def test_bad_header_handled_without_crash(self):
        data=bytearray(doom_fixture());data[:4]=b'XXXX'
        cpu,dev,log=boot_with_data(bytes(data))
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: no valid E1M1/MAP01 WAD map',log)

if __name__=='__main__':unittest.main()
