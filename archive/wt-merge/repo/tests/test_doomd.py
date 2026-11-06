import re,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from rv32_qwenputer import CPU
from merge_elf import parse

def syms(name):
    out=subprocess.check_output(['readelf','-sW',str(ROOT/'build'/name)],text=True)
    return {l.split()[-1]:int(l.split()[1],16) for l in out.splitlines() if len(l.split())>=8 and l.split()[0].rstrip(':').isdigit()}

class DoomdTakeover(unittest.TestCase):
    def test_kernel_core_fits_below_app_ram(self):
        k=syms('kernel.elf')
        self.assertLessEqual(k['__core_end'],0x570)
        self.assertEqual(k['qos_framebuffer']+768,k['__core_end'])
        for s in ('qos_input_mailbox','qos_disk_mailbox','qos_framebuffer'):
            self.assertLess(k[s],k['__core_end'],s)   # mailboxes + fb stay resident
        self.assertLessEqual(k['__ov_start'],0x570)
    def test_doomd_regions(self):
        d=syms('doomd.elf'); ent,segs=parse((ROOT/'build/doomd.elf').read_bytes())
        self.assertEqual(ent,0x41000)
        self.assertEqual(d['__app_ram_start'],0x570); self.assertEqual(d['__stack_top'],0x8000)
        self.assertLessEqual(d['__bss_end'],d['__stack_limit'])
        for va,blob,fl in segs:
            if fl&1: self.assertTrue(0x41000<=va and va+len(blob)<=0x78000)
            else: self.assertTrue(0x21000<=va and va+len(blob)<=0x3f000,hex(va))
    def test_takeover_runs_and_warm_reboots(self):
        cpu=CPU(str(ROOT/'build/qwenos-doomd.elf'))
        for _ in range(3000000):
            if cpu.halted:break
            cpu.step()
        log=''.join(cpu.output)
        self.assertTrue(cpu.halted and cpu.exitcode==0,log[-300:])
        for frag in ('QWENOS_DOOMD_BOOT','doomd: takeover','DOOMD_STUB_OK','QWENOS_DOOMD_EXIT'):
            self.assertIn(frag,log)
        self.assertEqual(log.count('QWENOS_BOOT_OK'),2)   # boot, takeover, warm reboot
        words=int(re.search(r'free RAM words (\d+)',log).group(1))
        d=syms('doomd.elf'); self.assertEqual(words*4,d['__stack_limit']-d['__bss_end'])
        self.assertGreaterEqual(words*4,29000)
        k=syms('kernel-doomd.elf')
        fb=bytes(cpu.mem[k['qos_framebuffer']:k['qos_framebuffer']+768])
        self.assertTrue(any(fb))   # framebuffer content survived/was repainted
        # kernel stack never overflowed into the mailbox/vars it sits above
        self.assertEqual(k['__tstack_top']-k['__tstack_limit'],64)
        self.assertEqual((k['qos_input_mailbox'],k['qos_disk_mailbox'],k['qos_framebuffer']),(0x154,0x15c,0x270))
if __name__=='__main__':unittest.main()
