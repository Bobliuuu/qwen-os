#!/usr/bin/env python3
"""Run the QwenOS kernel probe INSIDE Qwenputer's merged neural checkpoint.

Prerequisites: Qwenputer experimental/riscv on PYTHONPATH, a Qwenputer
Qwen3.5-4B checkpoint, transformers, torch, CUDA GPU (recommended).
This does not use host-side RISC-V instruction execution: the reference CPU
is only used to check each circuit token for exact correspondence.
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('model', help='directory of the actual merged Qwenputer checkpoint')
    p.add_argument('--elf',default='build/qwenos-model-probe.elf')
    p.add_argument('--max-text',type=int,default=240)
    p.add_argument('--max-chip',type=int,default=50000)
    p.add_argument('--slow',action='store_true')
    args=p.parse_args()
    from chipformer.rv import bridge, chat, elf, ref
    if not Path(args.elf).is_file():
        p.error(f'firmware not found: {args.elf}; run make model-probe')
    cpu=ref.Machine.from_program(elf.program(args.elf))
    bridge.park(cpu)
    oracle=ref.Machine.from_program(elf.program(args.elf))
    bridge.park(oracle)
    q=chat.RvChat(args.model,fast=not args.slow)
    ids=q.prompt_ids([{'role':'user','content':'Use calc to evaluate 1 + 1.'}])
    lock=bridge.Session(q.T,oracle)
    lock.history(ids)
    result=q.generate(ids,cpu,max_new=args.max_text,max_chip=args.max_chip,
                      check_head=True,lock=lock,verbose=True)
    text=q.text_of(result['tokens'])
    report={'model':args.model,'firmware':args.elf,'text':text,
            'chip_tokens':result['chip_tokens'],
            'text_tokens':result['text_tokens'],
            'head_mismatch':result['head_mismatch'],
            'lock_error':result['lock_error']}
    print(json.dumps(report,indent=2))
    if 'QWENOS_MODEL_PROBE_OK' not in text:
        sys.exit('Model did not emit the expected QwenOS probe success marker.')
    if result['lock_error'] is not None:
        sys.exit('Model circuit diverged from official Qwenputer CPU reference.')
    if result['head_mismatch']:
        sys.exit('Model logits disagreed with compiled circuit on chip-owned text tokens.')
    print('PASS: QwenOS kernel probe executed inside compiled Qwenputer model')

if __name__=='__main__':main()
