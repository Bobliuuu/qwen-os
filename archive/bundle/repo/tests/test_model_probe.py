"""The model-specific bridge must remain a bootable separate RV32 ELF."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from rv32_qwenputer import CPU

class ModelProbeTests(unittest.TestCase):
 def test_firmware_parks_then_resumes_with_special_bridge_tokens(self):
  cpu=CPU(str(ROOT/'build/qwenos-model-probe.elf'))
  for _ in range(12000):
   if cpu.halted:break
   cpu.step()
  self.assertTrue(cpu.halted)
  self.assertEqual(cpu.exitcode,0)
  self.assertEqual(cpu.byte_events,[])
  cpu.halted=False;cpu.exitcode=None
  for _ in range(12000):
   if cpu.halted:break
   cpu.step()
  self.assertTrue(cpu.halted)
  self.assertEqual(cpu.exitcode,0)
  self.assertEqual(cpu.byte_events[0],256)
  self.assertEqual(cpu.byte_events[-1],257)
  self.assertEqual(bytes(cpu.byte_events[1:-1]),b'QWENOS_MODEL_PROBE_OK\n')
 def test_park_pc_is_executable_rom(self):
  cpu=CPU(str(ROOT/'build/qwenos-model-probe.elf'))
  for _ in range(12000):
   if cpu.halted:break
   cpu.step()
  self.assertTrue(0x40000<=cpu.pc<0x60000)
  self.assertEqual(cpu.pc&3,0)
