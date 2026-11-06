#!/bin/bash
# Runs ON the GPU box (p4d: 8 GPUs; g5: set NGPU=1 DRY=1). Reads a chunk plan (name target A:B [extra args]).
# Chunk i goes to GPU (i mod NGPU); each GPU runs its chunks sequentially. Logs/results: ~/out/<chunk>/
# Usage: ./run_chunks_p4d.sh ~/chunks.plan     env: NGPU=8 DRY=1 MODEL=~/q4-rv1 DISK=~/repo/E1.lambda.img
# Fetch from Mac: out/model/fetch_chunks.sh <ip>
PLAN=${1:?plan}; NGPU=${NGPU:-8}; MODEL=${MODEL:-$HOME/q4-rv1}; DISK=${DISK:-$HOME/repo/E1.lambda.img}
export PYTHONPATH=$HOME/qwenputer/experimental/riscv; cd ~/repo
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
      if [ -n "$DRY" ]; then M="--dry-run"; else M="$MODEL"; fi
      CUDA_VISIBLE_DEVICES=$g ~/venv/bin/python tools/model_doom_qwen.py $M --elf build/qwenos-doomdmc.elf --disk $DISK \
        --target $target --segment-range $range --out $o/console.bin --result-json $o/result.json $extra > $o/run.log 2>&1
      echo "$name rc=$? gpu=$g" >> $HOME/out/status.log
    done <<< "${Q[$g]}" ) &
done
wait; echo ALL_DONE >> $HOME/out/status.log
