"""Interactive-shell tests on the Python reference CPU (+ rv32_fast for the DOOM takeover case)."""
import re,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import keysched
from rv32_qwenputer import CPU
LIVE=ROOT/'build/qwenos-live.elf';KELF=ROOT/'build/kernel-live.elf'

def sym(elf,name):
    out=subprocess.check_output(['readelf','-sW',str(elf)],text=True)
    for l in out.splitlines():
        f=l.split()
        if len(f)>=8 and f[-1]==name:return int(f[1],16)
    raise KeyError(name)

def session(text,limit=400000,extra=''):
    cpu=CPU(str(LIVE));kb=sym(KELF,'qos_input_mailbox');pk=sym(KELF,'qos_key_park')
    d=keysched.Driver(cpu,kb,pk,keysched.parse(keysched.type_lines(text)+extra))
    out=d.run(limit);return cpu,d,out

class LiveShell(unittest.TestCase):
    def test_prompt_is_first_output_and_cheap(self):
        cpu,d,out=session('')
        self.assertEqual(out,'$ ')                      # no banner, no boot script
        self.assertLess(cpu.steps,300)                  # cold boot -> prompt, parked waiting for a key
    def test_commands_echo_and_exit(self):
        cpu,d,out=session('ls\necho hi there > /tmp/note\ncat /tmp/note\nnope\nrun /bin/nope\nrun /bin/paint\nexit\n')
        self.assertEqual(cpu.exitcode,0)
        self.assertTrue(out.startswith('$ ls\n/README\n/bin/sh\n'))
        self.assertIn('/bin/doomd\n/tmp/note\n/tmp/log\n$ echo hi there > /tmp/note\n$ cat /tmp/note\nhi there\n$ nope\n?\n$ run /bin/nope\n?\n$ run /bin/paint\npaint: framebuffer changed\n$ exit\n',out)
    def test_backspace_and_empty_line(self):
        cpu,d,out=session('lx\x08s\n\n')
        self.assertIn('$ lx\x08 \x08s\n/README',out); self.assertTrue(out.endswith('$ \n$ '))
    def test_key_ring_queues_and_drops_oldest(self):
        cpu=CPU(str(LIVE));kb=sym(KELF,'qos_input_mailbox')
        for i,c in enumerate('abcdef'):cpu.store(kb+4+(i&3),1,ord(c))   # device pushed 6 keys before the guest polled
        cpu.store(kb,4,6)
        for _ in range(2000):cpu.step()
        out=''.join(cpu.output)
        self.assertEqual(out,'$ cdef')   # a,b overwritten by e,f -> guest reads c d e f in order
    def test_run_doomd_stub_takes_over_and_returns(self):
        cpu,d,out=session('run /bin/doomd\nexit\n',limit=2000000)
        self.assertEqual(cpu.exitcode,0)
        self.assertRegex(out,r'(?s)doomd: takeover\n.*DOOMD_STUB_OK\nQWENOS_DOOMD_EXIT\n\$ exit\n')

DOOM=ROOT/'build/qwenos-live-doomdmc-m3.elf';E1=ROOT/'../engine/DMC100-Doom/build/sw/nor/E1.img'
FAST=ROOT/'build/rv32_fast'
@unittest.skipUnless(DOOM.exists() and E1.exists() and FAST.exists(),'live DOOM image / E1.img / rv32_fast needed')
class LiveDoom(unittest.TestCase):
    def run_fast(self,sched,frames=3):
        with tempfile.TemporaryDirectory() as td:
            s=Path(td)/'s.txt';s.write_text(keysched.type_lines('run /bin/doomd\n')+sched)
            o=Path(td)/'o.bin'
            r=subprocess.run([str(FAST),'-W','%x'%sym(KELF,'qos_key_park'),'-K',str(s),'-F',str(frames),str(DOOM),str(E1),
                '%x'%sym(KELF,'qos_input_mailbox'),'%x'%sym(KELF,'qos_disk_mailbox'),str(o),'200000000'],capture_output=True,text=True)
            ram=Path(str(o)+'.ram').read_bytes();fb=sym(KELF,'qos_framebuffer')
            return r.stderr,o.read_bytes(),ram[fb:fb+768]
    def test_typed_launch_reaches_e1m1_and_key_is_not_lost_across_takeover(self):
        err,con,fb0=self.run_fast('')
        self.assertIn(b'DOOMD_LEVEL_START e1m1',con);self.assertIn('exit=0 frames=3',err)
        self.assertTrue(any(fb0))
        # 'd' (turn right) pushed at instruction 2500: after the kernel entered takeover_run (~1.9k) and before
        # doomd's first key poll. It must sit in the ring and still turn the player.
        err,con,fb1=self.run_fast('2500 d\n')
        self.assertNotEqual(fb0,fb1)
        err,con,fb2=self.run_fast('frame 1 d\n')       # same key delivered later, while the engine runs
        self.assertNotEqual(fb0,fb2)

if __name__=='__main__':unittest.main()
