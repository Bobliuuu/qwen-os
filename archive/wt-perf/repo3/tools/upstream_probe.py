#!/usr/bin/env python3
"""Two-phase Qwenputer *official reference CPU* test of the OS model bridge.

This test is NOT execution inside the neural model.  Its intended use is a
networked GitHub Actions runner or a checkout with PYTHONPATH set to upstream.
"""
import argparse
import json


def run(elf_path):
    from chipformer.rv import elf, ref, spec
    machine = ref.Machine.from_program(elf.program(elf_path))
    def phase(budget):
        emitted = []
        start = machine.steps
        while not machine.halted and machine.steps - start < budget:
            rec = machine.record()
            for token in rec:
                if spec.family(token)[0] == 'BYTE':
                    emitted.append(spec.family(token)[1])
            if machine.fault is not None:
                raise AssertionError(f'upstream CPU fault: {machine.fault}')
        assert machine.halted and machine.exit_code == 0, (
            machine.steps, machine.exit_code, machine.fault)
        return emitted, machine.steps - start

    pre, pre_steps = phase(20000)
    assert pre == [], f'park should emit no tokens, got {pre}'
    machine.halted = False
    after, steps = phase(20000)
    assert after[0] == 256 and after[-1] == 257, after
    body = bytes(after[1:-1]).decode('ascii')
    assert body == 'QWENOS_MODEL_PROBE_OK\n', repr(body)
    print(json.dumps({'park_instructions':pre_steps,
                      'resume_instructions':steps,
                      'bridge_output':body,
                      'upstream_reference_passed':True}, indent=2))

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('elf',nargs='?',default='build/qwenos-model-probe.elf')
    run(parser.parse_args().elf)
