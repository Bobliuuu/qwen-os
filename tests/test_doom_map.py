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
        self.assertTrue(any(10 <= v <= 17 for v in values))
        self.assertGreaterEqual(len(values),3)
    def test_key_changes_guest_wall_projection(self):
        base,_,out1=boot_with_data(doom_fixture())
        rotated,_,out2=boot_with_data(doom_fixture(),key='d')
        self.assertEqual(base.exitcode,0)
        self.assertEqual(rotated.exitcode,0)
        self.assertIn('doom: WAD map geometry rendered',out2)
        fb=symbols()['framebuffer']
        self.assertNotEqual(base.mem[fb:fb+768],rotated.mem[fb:fb+768])
    def test_forward_movement_changes_guest_frame(self):
        base,_,_=boot_with_data(doom_fixture())
        moved,_,log=boot_with_data(doom_fixture(),key='w')
        fb=symbols()['framebuffer']
        self.assertEqual(moved.exitcode,0)
        self.assertIn('QWENOS_BOOT_OK',log)
        self.assertNotEqual(base.mem[fb:fb+768],moved.mem[fb:fb+768])

    def test_solid_walls_block_guest_movement(self):
        room=bytearray(doom_fixture())
        # Player starts eight units from the east wall, so the 16-unit step
        # would cross it and must be rejected by the guest collision routine.
        struct.pack_into('<h',room,0x210100,120)
        base,_,_=boot_with_data(bytes(room))
        moved,_,log=boot_with_data(bytes(room),key='w')
        fb=symbols()['framebuffer']
        self.assertEqual(moved.exitcode,0)
        self.assertIn('QWENOS_BOOT_OK',log)
        self.assertEqual(base.mem[fb:fb+768],moved.mem[fb:fb+768])

    def test_malformed_linedef_rejected_by_guest(self):
        data=bytearray(doom_fixture())
        struct.pack_into('<H',data,0x210200,65000)
        cpu,dev,log=boot_with_data(bytes(data))
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: no valid E1M1/MAP01 WAD map',log)
        self.assertNotIn('doom: WAD map geometry rendered',log)
    def test_real_sector_ceiling_changes_wall_projection(self):
        base,_,_ = boot_with_data(doom_fixture())
        short=bytearray(doom_fixture())
        struct.pack_into('<h',short,0x210402,32)
        lowered,_,log=boot_with_data(bytes(short))
        fb=symbols()['framebuffer']
        self.assertEqual(lowered.exitcode,0)
        self.assertIn('doom: WAD map geometry rendered',log)
        full_count=sum(10<=x<=17 for x in base.mem[fb:fb+768])
        short_count=sum(10<=x<=17 for x in lowered.mem[fb:fb+768])
        self.assertGreater(full_count,short_count)

    def test_invalid_sidedef_sector_rejected(self):
        bad=bytearray(doom_fixture())
        struct.pack_into('<H',bad,0x210500+28,65534)
        cpu,_,log=boot_with_data(bytes(bad))
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: no valid E1M1/MAP01 WAD map',log)

    def test_large_map_streams_geometry_without_loading_full_level(self):
        data=bytearray(doom_fixture())
        vertices=[(-64,-64),(128,-64),(128,64),(-64,64)] + [
            (300+i,300+i) for i in range(96)]
        lines=[(0,1),(1,2),(2,3),(3,0)] + [
            (4+i%95,5+i%95) for i in range(136)]
        vb=b''.join(struct.pack('<hh',*v) for v in vertices)
        lb=b''.join(struct.pack('<7H',a,b,1,0,0,0,65535) for a,b in lines)
        data[0x213000:0x213000+len(vb)]=vb
        data[0x212000:0x212000+len(lb)]=lb
        struct.pack_into('<II',data,0x300000+3*16,0x212000,len(lb))
        struct.pack_into('<II',data,0x300000+5*16,0x213000,len(vb))
        cpu,dev,log=boot_with_data(bytes(data))
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: WAD map geometry rendered',log)
        self.assertGreater(len(dev.reads),400)
        fb=symbols()['framebuffer']
        self.assertTrue(any(10<=v<=17 for v in cpu.mem[fb:fb+768]))

    def test_wad_with_more_than_256_lumps(self):
        data=bytearray(doom_fixture())
        directory=0x300000
        entries=[bytes(data[directory+i*16:directory+(i+1)*16]) for i in range(12)]
        dummy=struct.pack('<II8s',0,0,b'JUNK\0\0\0\0')
        entries=([dummy]*300)+entries
        struct.pack_into('<I',data,4,len(entries))
        for i,e in enumerate(entries):data[directory+16*i:directory+16*i+16]=e
        cpu,dev,log=boot_with_data(bytes(data))
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: WAD map geometry rendered',log)
        self.assertGreater(len(dev.reads),300)

    def test_bad_header_handled_without_crash(self):
        data=bytearray(doom_fixture());data[:4]=b'XXXX'
        cpu,dev,log=boot_with_data(bytes(data))
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: no valid E1M1/MAP01 WAD map',log)

if __name__=='__main__':unittest.main()
