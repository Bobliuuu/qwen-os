"""End-to-end guest DOOM-format map reader/render tests.

These assert actual RV32 guest execution, not Python rendering. The guest
renders with a real BSP front-to-back traversal; textures, sprites, monsters
and game logic are absent. Pixel format: bits 7-6 class (0 wall, 1 floor,
2 ceiling, 3 sky), bits 5-0 brightness.
The real-WAD test needs Freedoom (BSD) at ../wads/freedoom1.wad
or $QOS_FREEDOOM_WAD, and is skipped when absent.
"""
import os
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
            cpu.store(inject_addr+4,4,ord(key))   # ring slot 0
            cpu.store(inject_addr,4,1)            # seq=1: one key pushed
            injected=True
    return cpu,dev,''.join(cpu.output)

class DoomMapTests(unittest.TestCase):
    def test_guest_parses_doom_map_and_renders_pixels(self):
        cpu,dev,log=boot_with_data(doom_fixture())
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: WAD map geometry rendered',log)
        self.assertIn('QWENOS_BOOT_OK',log)
        self.assertTrue(any(o==0x210300 for o,n,ok in dev.reads))   # VERTEXES
        self.assertTrue(any(o==0x210600 for o,n,ok in dev.reads))   # SEGS
        self.assertTrue(any(o==0x210700 for o,n,ok in dev.reads))   # SSECTORS
        fb=symbols()['qos_framebuffer']
        values=set(cpu.mem[fb:fb+768])
        self.assertEqual({v>>6 for v in values},{0,1,2})  # wall, floor, ceiling
        self.assertGreaterEqual(len(values),3)
    def test_key_changes_guest_wall_projection(self):
        base,_,out1=boot_with_data(doom_fixture())
        rotated,_,out2=boot_with_data(doom_fixture(),key='d')
        self.assertEqual(base.exitcode,0)
        self.assertEqual(rotated.exitcode,0)
        self.assertIn('doom: WAD map geometry rendered',out2)
        fb=symbols()['qos_framebuffer']
        self.assertNotEqual(base.mem[fb:fb+768],rotated.mem[fb:fb+768])
    def test_forward_movement_changes_guest_frame(self):
        base,_,_=boot_with_data(doom_fixture())
        moved,_,log=boot_with_data(doom_fixture(),key='w')
        fb=symbols()['qos_framebuffer']
        self.assertEqual(moved.exitcode,0)
        self.assertIn('QWENOS_BOOT_OK',log)
        self.assertNotEqual(base.mem[fb:fb+768],moved.mem[fb:fb+768])

    def test_solid_walls_block_guest_movement(self):
        room=bytearray(doom_fixture())
        # Player starts 28 units from the east wall, so the 16-unit step
        # would cross it and must be rejected by the guest collision routine.
        struct.pack_into('<h',room,0x210100,100)
        base,_,_=boot_with_data(bytes(room))
        moved,_,log=boot_with_data(bytes(room),key='w')
        fb=symbols()['qos_framebuffer']
        self.assertEqual(moved.exitcode,0)
        self.assertIn('QWENOS_BOOT_OK',log)
        self.assertEqual(base.mem[fb:fb+768],moved.mem[fb:fb+768])

    def test_malformed_seg_vertex_rejected_by_guest(self):
        data=bytearray(doom_fixture())
        struct.pack_into('<H',data,0x210600,65000)   # SEG 0 v1 out of range
        cpu,dev,log=boot_with_data(bytes(data))
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: geometry read error',log)
        self.assertNotIn('doom: WAD map geometry rendered',log)
    def test_real_sector_ceiling_changes_wall_projection(self):
        base,_,_ = boot_with_data(doom_fixture())
        short=bytearray(doom_fixture())
        struct.pack_into('<h',short,0x210402,64)
        lowered,_,log=boot_with_data(bytes(short))
        fb=symbols()['qos_framebuffer']
        self.assertEqual(lowered.exitcode,0)
        self.assertIn('doom: WAD map geometry rendered',log)
        full_count=sum(x>>6==0 for x in base.mem[fb:fb+768])
        short_count=sum(x>>6==0 for x in lowered.mem[fb:fb+768])
        self.assertGreater(full_count,short_count)

    def test_invalid_sidedef_sector_rejected(self):
        bad=bytearray(doom_fixture())
        struct.pack_into('<H',bad,0x210500+28,65534)
        cpu,_,log=boot_with_data(bytes(bad))
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: geometry read error',log)

    def test_large_vertex_table_streams_from_disk(self):
        # >1280 vertices exceeds the guest vertex cache: vertices are then
        # fetched per seg with 4-byte disk reads.
        data=bytearray(doom_fixture())
        vertices=[(-64,-64),(128,-64),(128,64),(-64,64)]+[(300+i%50,300+i%70) for i in range(1400)]
        vb=b''.join(struct.pack('<hh',*v) for v in vertices)
        data[0x220000:0x220000+len(vb)]=vb
        struct.pack_into('<II',data,0x300000+5*16,0x220000,len(vb))
        cpu,dev,log=boot_with_data(bytes(data))
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('doom: WAD map geometry rendered',log)
        self.assertTrue(any(0x220000<=o<0x220000+len(vb) and n==4 for o,n,ok in dev.reads))
        fb=symbols()['qos_framebuffer']
        self.assertTrue(any(v>>6==0 for v in cpu.mem[fb:fb+768]))

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

FREEDOOM=Path(os.environ.get('QOS_FREEDOOM_WAD','../wads/freedoom1.wad'))

@unittest.skipUnless(FREEDOOM.exists(),'Freedoom IWAD not present')
class RealWadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from interactive_frames import play
        cls.cpu,cls.dev,cls.frames=play(str(ROOT/'build/qwenos.elf'),'wd',str(FREEDOOM),6_000_000)

    def test_e1m1_renders_with_bsp_in_guest(self):
        self.assertEqual(self.cpu.exitcode,0)
        self.assertEqual(len(self.frames),3)
        self.assertTrue(all(ok for _,_,ok in self.dev.reads))
        classes={v>>6 for v in self.frames[0]}
        self.assertTrue({0,1}<=classes,classes)   # walls and floors
        self.assertGreaterEqual(len({v&63 for v in self.frames[0]}),6)  # lit/shaded
        reads=[o for o,n,ok in self.dev.reads]
        self.assertTrue(any(106452<=o<125520 for o in reads))   # NODES streamed
        self.assertTrue(any(79040<=o<103724 for o in reads))    # SEGS streamed

    def test_frames_change_and_fit_instruction_budget(self):
        self.assertNotEqual(self.frames[0],self.frames[1])
        self.assertNotEqual(self.frames[1],self.frames[2])
        steps=self.cpu.frame_steps
        self.assertLess(steps[2]-steps[1],700_000)   # a frame, incl. movement collision
        self.assertLess(steps[2],2_000_000)

    def test_app_ram_budget(self):
        out=subprocess.check_output(['readelf','-SW',str(ROOT/'build/doom.elf')],text=True)
        bss=[l for l in out.splitlines() if '.bss' in l][0].split()
        size=int(bss[bss.index('.bss')+5],16)
        self.assertLess(size,0x5800-0x1000)   # leave >=4 KiB headroom in app RAM


if __name__=='__main__':unittest.main()
