#!/bin/bash
# periodically pull prod1 results from the Modal volume into out/model/chunks/ (run.log/console.bin/result.json per chunk)
export PATH=$HOME/.pyenv/shims:$PATH; cd /Users/jhome/qwenos-work/out/model; mkdir -p chunks
while true; do modal volume get --force qwenos-results /prod1 chunks/ >/dev/null 2>&1; modal volume get --force qwenos-results /prod1p chunks/ >/dev/null 2>&1; echo "$(date +%T) $(ls chunks/prod1/*/result.json 2>/dev/null | wc -l) done" >> sync_results.log; sleep 240; done
