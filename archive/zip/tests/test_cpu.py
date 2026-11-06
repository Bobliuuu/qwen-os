import sys
import re
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from rv32_qwenputer import CPU

class BootTests(unittest.TestCase):
    def test_real_guest_execution_and_framebuffer(self):
        cpu=CPU(str(ROOT/'build/qwenos.elf'))
        for _ in range(230_000):
            if cpu.halted:break
            cpu.step()
        self.assertEqual(cpu.exitcode,0)
        log=''.join(cpu.output)
        for fragment in ('pid 1','$ cat /README','hello from QwenOS','paint: framebuffer changed','raycast: frame rendered','QWENOS_BOOT_OK'):
            self.assertIn(fragment,log)
        symbols=subprocess.check_output(['readelf','-sW',str(ROOT/'build/kernel.elf')],text=True)
        m=re.search(r'\b([0-9a-f]{8})\s+768\s+OBJECT\s+LOCAL\s+DEFAULT\s+\d+\s+framebuffer\b',symbols)
        self.assertIsNotNone(m,'kernel framebuffer symbol missing')
        addr=int(m.group(1),16)
        pix=cpu.mem[addr:addr+32*24]
        self.assertEqual(pix[0],1)
        self.assertEqual(pix[12*32+15],9)
        self.assertGreater(len(set(pix)),2)
        self.assertGreater(cpu.steps,10000)

if __name__=='__main__':unittest.main()

def kernel_symbols():
    output=subprocess.check_output(['readelf','-sW',str(ROOT/'build/kernel.elf')],text=True)
    return {line.split()[-1]:int(line.split()[1],16) for line in output.splitlines()
            if len(line.split())>=8 and line.split()[0].rstrip(':').isdigit()}

class KernelAbiTests(unittest.TestCase):
    def test_mailbox_key_event_is_consumed_by_guest(self):
        cpu=CPU(str(ROOT/'build/qwenos.elf'))
        addr=kernel_symbols()['qos_input_mailbox']
        injected=False
        for _ in range(230_000):
            if cpu.halted:break
            cpu.step()
            if not injected and len(cpu.output)>=12:
                # Deliver a device event while firmware is running, after BSS init.
                cpu.store(addr+4,4,ord('K'))
                cpu.store(addr,4,1)
                injected=True
        self.assertTrue(injected)
        self.assertEqual(cpu.exitcode,0)
        self.assertIn('QwenOS input: K',''.join(cpu.output))

    def test_keyboard_changes_rendered_guest_frame(self):
        elf=str(ROOT/'build/qwenos.elf')
        addr=kernel_symbols()['qos_input_mailbox']
        baseline=CPU(elf);baseline.run(230000)
        self.assertEqual(baseline.exitcode,0)
        shifted=CPU(elf)
        injected=False
        for _ in range(230_000):
            if shifted.halted:break
            shifted.step()
            if not injected and '$ run /bin/raycast\n' in ''.join(shifted.output):
                shifted.store(addr+4,4,ord('d'))
                shifted.store(addr,4,2)
                injected=True
        self.assertTrue(injected)
        self.assertEqual(shifted.exitcode,0)
        fb=kernel_symbols()['framebuffer']
        self.assertNotEqual(baseline.mem[fb:fb+768],shifted.mem[fb:fb+768])
        self.assertEqual(shifted.mem[fb+12*32+19],9)
        import zlib
        self.assertNotEqual(zlib.crc32(baseline.mem[fb:fb+768]),zlib.crc32(shifted.mem[fb:fb+768]))

    def test_separate_stacks_and_canaries(self):
        cpu=CPU(str(ROOT/'build/qwenos.elf'))
        for _ in range(230_000):
            if cpu.halted:break
            cpu.step()
        self.assertEqual(cpu.exitcode,0)
        base=kernel_symbols()['app_stacks']
        for level in range(2):
            stack=cpu.mem[base+1536*level:base+1536*(level+1)]
            self.assertEqual(stack[:16],bytes([0xA5])*16)
            self.assertTrue(any(b!=0 for b in stack[32:]),'app stack was never used')
        self.assertEqual(base % 16,0)
        self.assertTrue(any(cpu.mem[base+512:base+1536]))
        self.assertTrue(any(cpu.mem[base+1536+512:base+3072]))

class MemorySafetyTests(unittest.TestCase):
    def test_instruction_rom_is_not_writable(self):
        cpu=CPU(str(ROOT/'build/qwenos.elf'))
        with self.assertRaises(RuntimeError):cpu.store(0x40000,4,0)

    def test_drom_is_not_writable(self):
        cpu=CPU(str(ROOT/'build/qwenos.elf'))
        with self.assertRaises(RuntimeError):cpu.store(0x20000,1,0)

    def test_rom_is_not_readable_as_data(self):
        cpu=CPU(str(ROOT/'build/qwenos.elf'))
        with self.assertRaises(RuntimeError):cpu.load(0x40000,4)
