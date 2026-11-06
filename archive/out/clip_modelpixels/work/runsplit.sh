#!/bin/zsh
export PYTHONPATH=/Users/jhome/qwenos-work/out/model/qwenputer_patched/riscv:/private/tmp/mp/bundle/tools
cd /Users/jhome/qwenos-work/out/clip_modelpixels/work
exec python3 fbsplit.py --frame $1 --snaps orig --sym-elf /private/tmp/mp/bundle/build/doomd-sym.elf --out snaps > logs/split$1.log 2>&1
