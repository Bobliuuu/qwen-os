#!/bin/bash
# Runs ON a GPU box (p4d: 8 GPUs; Lambda A100: NGPU=1). Fleet runner for the chunk-ROM clip (replaces run_chunks_p4d.sh's hard-coded
# ELF/disk): reads chunks.plan lines `name target A:B extra...`, chunk i -> GPU (i mod NGPU), each GPU runs its chunks in order.
# Layout (made by sync_crx_to_box.sh): ~/crx/{build/qwenos-e1m1.elf, build/doomd-sym.elf, build/kernel-doomd.elf, build/crx-plan.json, E1.img, tools/*.py}
# Usage: ./run_chunks_crx.sh ~/crx/chunks.plan     env: NGPU=8 DRY=1 MODEL=~/q4-rv1 PY=~/venv/bin/python QWENPUTER=~/qwenputer/experimental/riscv
PLAN=${1:?plan}; NGPU=${NGPU:-8}; MODEL=${MODEL:-$HOME/q4-rv1}; PY=${PY:-$HOME/venv/bin/python}
export PYTHONPATH=${QWENPUTER:-$HOME/qwenputer/experimental/riscv}; cd ~/crx
i=0; declare -a Q
while read -r name target range extra; do
  [[ -z "$name" || "$name" == \#* ]] && continue
  Q[$((i % NGPU))]+="$name|$target|$range|$extra"$'\n'; i=$((i+1))
done < "$PLAN"
for g in $(seq 0 $((NGPU-1))); do
  [ -n "${Q[$g]}" ] || continue
  ( while IFS='|' read -r name target range extra; do
      [ -n "$name" ] || continue
      o=$HOME/out/$name; mkdir -p $o
      [ -f $o/result.json ] && continue                      # resume: finished chunks are kept
      if [ -n "$DRY" ]; then M="--dry-run"; else M="$MODEL"; fi
      CUDA_VISIBLE_DEVICES=$g $PY tools/model_doom_qwen.py $M --elf build/qwenos-e1m1.elf --kernel-elf build/kernel-doomd.elf --disk E1.img \
        --target $target --segment-range $range --out $o/console.bin --result-json $o/result.json $extra > $o/run.log 2>&1
      echo "$name rc=$? gpu=$g" >> $HOME/out/status.log
    done <<< "${Q[$g]}" ) &
done
wait; echo ALL_DONE >> $HOME/out/status.log
