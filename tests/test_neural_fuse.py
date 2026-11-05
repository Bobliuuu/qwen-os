"""HOST-ONLY tests of tools/neural_fuse.py (the LIJ superinstruction reference model).
Skipped unless the upstream Qwenputer reference (chipformer.rv.ref) is on PYTHONPATH."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import neural_fuse as F

try:
    from chipformer.rv import ref, spec as S
    HAVE = True
except ImportError:
    HAVE = False


class RomLayout(unittest.TestCase):
    def test_lij_rom_word_roundtrip(self):
        rng = random.Random(7)
        for _ in range(2000):
            rd, imm = rng.randint(1, 31), rng.randint(-(1 << 19), (1 << 19) - 1)
            self.assertEqual(F.lij_fields(F.lij_rom_word(rd, imm)), (rd, imm))
        self.assertEqual(F.lij_fields(F.lij_rom_word(31, -(1 << 19))), (31, -(1 << 19)))


@unittest.skipUnless(HAVE, 'needs qwenputer/experimental/riscv on PYTHONPATH')
class Equivalence(unittest.TestCase):
    def test_lui_addi_pair_state_and_tokens(self):
        # lui t0, 0x20 ; addi t0, t0, 0x123 ; exit
        words = [F.lui(5, 0x20), F.addi(5, 5, 0x123), F.addi(17, 0, 93), 0x73]
        st = F.check_equivalence(words)
        self.assertEqual(st['fused_records'], 1)
        self.assertEqual(st['fusable_positions'], 1)
        # sequential: lui 0x20000 = V F1, addi 0x20123 = V F1 -> 4 tokens; fused: 1 token (J)
        self.assertEqual((st['tokens_plain'], st['tokens_fused']), (6, 3))  # incl. addi a7 + ecall exit
        self.assertEqual(st['instr'], 4)

    def test_auipc_addi_pair(self):
        words = [F.auipc(10, 3), F.addi(10, 10, -4), F.addi(17, 0, 93), 0x73]
        self.assertEqual(F.check_equivalence(words)['fused_records'], 1)

    def test_not_fused_when_result_too_wide_or_rd_differs(self):
        wide = [F.lui(5, 0x12345), F.addi(5, 5, 1), F.addi(17, 0, 93), 0x73]
        self.assertEqual(F.check_equivalence(wide)['fusable_positions'], 0)
        other = [F.lui(5, 1), F.addi(6, 5, 1), F.addi(17, 0, 93), 0x73]
        self.assertEqual(F.check_equivalence(other)['fusable_positions'], 0)
        x0 = [F.lui(0, 1), F.addi(0, 0, 1), F.addi(17, 0, 93), 0x73]
        self.assertEqual(F.check_equivalence(x0)['fusable_positions'], 0)

    def test_branch_into_the_middle_of_a_pair_runs_the_original_addi(self):
        # 0: addi t1,x0,5 ; 1: beq x0,x0,+8 (-> 3, the addi of the pair) ; 2: lui t0,0x10 ;
        # 3: addi t0,t0,7 ; 4,5: exit.  Position 2/3 are a fusable pair; entering at 3 must run addi alone.
        words = [F.addi(6, 0, 5), F.enc_b(0, 0, 0, 8), F.lui(5, 0x10), F.addi(5, 5, 7),
                 F.addi(17, 0, 93), 0x73]
        st = F.check_equivalence(words)
        self.assertEqual(st['fusable_positions'], 1)
        self.assertEqual(st['fused_records'], 0)  # never executed fused: the branch skipped the lui

    def test_signed_20_boundary(self):
        for hi, lo, ok in ((0x7F, 0x7FF, 1), (0x80, 0, 0), (0xFFF80, 0, 1), (0xFFF7F, 0, 0), (0xFFF80, -1, 0)):
            words = [F.lui(7, hi), F.addi(7, 7, lo), F.addi(17, 0, 93), 0x73]
            st = F.check_equivalence(words)
            self.assertEqual(st['fusable_positions'], ok, (hex(hi), lo))

    def test_randomized_programs_bit_exact(self):
        rng = random.Random(20260404)
        fused = 0
        for _ in range(250):
            st = F.check_equivalence(F.random_program(rng))
            fused += st['fused_records']
        self.assertGreater(fused, 100)  # the generator really exercises the fused path


if __name__ == '__main__':
    unittest.main()
