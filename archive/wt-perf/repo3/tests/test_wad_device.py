import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from wad_device import run,fixture,DEMO_LUMP_OFFSET,DEMO_DIRECTORY_OFFSET,DEMO_DATA,WadDevice,doom_fixture
from rv32_qwenputer import CPU

class WadDeviceTests(unittest.TestCase):
    def test_wad_lump_loaded_from_2mb_and_3mb_offsets(self):
        cpu,device,out=run(str(ROOT/'build/qwenos.elf'))
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('asset: WAD read and verified',out)
        self.assertIn('QWENOS_BOOT_OK',out)
        self.assertEqual(device.reads[:3],[(0,12,True),(DEMO_DIRECTORY_OFFSET,16,True),(DEMO_LUMP_OFFSET,32,True)])
        self.assertIn('doom: WAD map geometry rendered',out)
        self.assertGreater(len(fixture()),0x300000)
        self.assertEqual(len(DEMO_DATA),32)
    def test_out_of_bounds_disk_request_reports_failure(self):
        cpu=CPU(str(ROOT/'build/qwenos.elf'))
        dev=WadDevice(cpu,b'1234')
        base=dev.base
        cpu.store(base+4,4,20)
        cpu.store(base+8,4,8)
        cpu.store(base,4,1)
        dev.tick()
        self.assertEqual(dev.word(16),2)
        self.assertEqual(dev.word(12),1)
    def test_response_not_replayed(self):
        cpu=CPU(str(ROOT/'build/qwenos.elf'))
        dev=WadDevice(cpu,b'abcdef')
        base=dev.base
        cpu.store(base+4,4,2)
        cpu.store(base+8,4,3)
        cpu.store(base,4,1)
        dev.tick()
        self.assertEqual(bytes(cpu.mem[base+20:base+23]),b'cde')
        dev.tick()
        self.assertEqual(len(dev.reads),1)

class UpstreamAdapterTests(unittest.TestCase):
    def test_qwenputer_word_ram_mailbox(self):
        from upstream_ref import ReferenceDiskDevice
        class Fake:
            ram=[0]*8192
        ram=Fake()
        base=0x100
        dev=ReferenceDiskDevice(ram,base,b'abcdefghijklmnop')
        dev.put_u32(base,1)           # request_seq
        dev.put_u32(base+4,3)         # byte offset
        dev.put_u32(base+8,6)         # length
        dev.tick()
        self.assertEqual(dev.get_u32(base+12),1)
        self.assertEqual(dev.get_u32(base+16),1)
        payload=bytes((ram.ram[(base+20+i)//4] >> ((base+20+i)%4*8)) & 255 for i in range(6))
        self.assertEqual(payload,b'defghi')
        self.assertEqual(dev.reads,[(3,6,True)])
