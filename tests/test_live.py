"""pty-driven end-to-end test of the live terminal runner (tools/qwenos_live.sh -> rv32_fast -L).
The test plays the human: it types into a pseudo-terminal and reads what a terminal would show."""
import fcntl,os,pty,re,select,struct,subprocess,sys,termios,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
E1=ROOT/'.deps/engine/DMC100-Doom/build/sw/nor/E1.img'
FAST=ROOT/'build/rv32_fast'

class Term:
    def __init__(self,elf,extra=(),env=None,rows=40,cols=100):
        self.m,s=pty.openpty()
        fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,0,0))
        e=dict(os.environ);e.update(env or {});e['ELF']=str(elf)
        self.p=subprocess.Popen([str(ROOT/'tools/qwenos_live.sh'),*extra],stdin=s,stdout=s,stderr=s,env=e,close_fds=True)
        os.close(s);self.buf=b''
    def read(self,t=0.05):
        r,_,_=select.select([self.m],[],[],t)
        if r:
            try:d=os.read(self.m,65536)
            except OSError:return False
            if not d:return False
            self.buf+=d
        return True
    def expect(self,pat,timeout=60,start=0):
        end=time.time()+timeout
        while time.time()<end:
            if re.search(pat,self.buf[start:]):return True
            if not self.read() and self.p.poll() is not None:break
        return bool(re.search(pat,self.buf[start:]))
    def type(self,s,gap=0.01):
        for ch in s:
            os.write(self.m,ch.encode());time.sleep(gap)
    def finish(self,timeout=20):
        end=time.time()+timeout
        while time.time()<end and self.p.poll() is None:self.read()
        while self.read(0.05):pass
        return self.p.poll()

def need(*ps):
    return all(Path(p).exists() for p in ps)

@unittest.skipUnless(need(FAST,ROOT/'build/qwenos-live.elf',E1),'build/rv32_fast, qwenos-live.elf and E1.img needed')
class LiveShellPty(unittest.TestCase):
    def test_typed_shell_session_and_quit(self):
        t=Term(ROOT/'build/qwenos-live.elf')
        self.assertTrue(t.expect(rb'\$ '))
        t.type('ls\r');self.assertTrue(t.expect(rb'/bin/doomd\r\n/tmp/note'))
        t.type('echo hix\x7f > /tmp/note\r');t.type('cat /tmp/note\r')
        self.assertTrue(t.expect(rb'\r\nhi\r\n'))                   # backspace removed the x
        self.assertIn(b'\x08 \x08',t.buf)                       # guest echoed the erase
        t.type('bogus\r');self.assertTrue(t.expect(rb'\?\r\n'))
        t.type('\x1d')                                          # Ctrl-]: host quit, not seen by guest
        self.assertEqual(t.finish(),0)
        self.assertRegex(t.buf,rb'QwenOS live: quit key after \d+ guest instructions, 0 frames shown')

    def test_run_stub_doomd_returns_to_prompt(self):
        t=Term(ROOT/'build/qwenos-live.elf')
        self.assertTrue(t.expect(rb'\$ '))
        t.type('run /bin/doomd\r')
        self.assertTrue(t.expect(rb'QWENOS_DOOMD_EXIT\r\n\$ '))   # warm reboot, new prompt
        t.type('exit\r');self.assertEqual(t.finish(),0)
        self.assertRegex(t.buf,rb'guest exited after')

DOOM=ROOT/'build/qwenos-live-doomdmc-m3.elf'
@unittest.skipUnless(need(FAST,DOOM,E1),'build/qwenos-live-doomdmc-m3.elf (OS=live ports/doomdmc/mkmode.sh 3) needed')
class LiveDoomPty(unittest.TestCase):
    def test_boot_type_run_doomd_play_quit(self):
        t=Term(DOOM,extra=('--fps','0'))
        self.assertTrue(t.expect(rb'\$ '))
        t.type('run /bin/doomd\r')
        self.assertTrue(t.expect(rb'\x1b\[\?1049h',120))          # first DOOM frame -> game screen
        self.assertTrue(t.expect(rb'frame [3-9] \|',120))         # several frames rendered (status line)
        n=len(t.buf)
        t.type('wwdf')                                            # real keys into the mailbox
        self.assertTrue(t.expect(rb'48;2;',30,n))                  # fb painted with 24-bit colours
        self.assertTrue(t.expect(rb'frame \d\d \|',120,n))
        t.type('\x1d');self.assertEqual(t.finish(),0)
        m=re.search(rb'QwenOS live: quit key after (\d+) guest instructions, (\d+) frames shown',t.buf)
        self.assertTrue(m);self.assertGreater(int(m.group(1)),3_000_000);self.assertGreaterEqual(int(m.group(2)),10)

@unittest.skipUnless(need(FAST,DOOM,E1),'live DOOM image needed (make live-doom builds it)')
class LiveTranscript(unittest.TestCase):
    def test_auto_tour_then_doom_frames_as_ascii(self):
        sys.path.insert(0,str(ROOT/'tools'))
        import live_transcript
        buf=live_transcript.run(2)
        self.assertIn(b'tier T0',buf)
        for pat in (rb'\$ help\r\n',rb'\$ ls\r\n/README',rb'hello qwenos\r\n',rb'\$ run /bin/doomd',rb'DOOMD_LEVEL_START e1m1'):
            self.assertRegex(buf,pat)
        fr=live_transcript.frames_ascii(buf)
        self.assertGreaterEqual(len(fr),2);self.assertGreater(len(set(''.join(fr[0]))),2)   # a real picture, not blank

if __name__=='__main__':unittest.main()
