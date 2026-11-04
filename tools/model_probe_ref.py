#!/usr/bin/env python3
"""Validate the Qwenputer park/GO/resume probe on independent RV32 interpreter.

This is NOT a model run. Use chipformer.rv.chat with the actual merged Qwenputer
checkpoint for that (see README). The probe is a temporary hardware handshake.
"""
import sys
from pathlib import Path
from rv32_qwenputer import CPU

def test(path):
    cpu=CPU(str(path))
    for _ in range(10000):
        if cpu.halted:break
        cpu.step()
    assert cpu.halted and cpu.exitcode==0, 'firmware failed to park'
    assert not cpu.output, 'park must be silent for Qwen bridge'
    # Qwenputer's GO continues immediately after the park ecall.
    cpu.halted=False
    cpu.exitcode=None
    for _ in range(10000):
        if cpu.halted:break
        cpu.step()
    out=''.join(cpu.output)
    assert cpu.halted and cpu.exitcode==0, (cpu.exitcode,out)
    assert cpu.byte_events[0] == 256 and cpu.byte_events[-1] == 257, cpu.byte_events
    assert 'QWENOS_MODEL_PROBE_OK' in out, out
    # Inspect full 9-bit BYTE events, not the lossy latin-1 console projection.
    print(f'PASS: Qwenputer model bridge probe parked and resumed; {cpu.steps} RV32 instructions')
    print(out)

if __name__=='__main__':test(Path(sys.argv[1] if len(sys.argv)>1 else 'build/qwenos-model-probe.elf'))
