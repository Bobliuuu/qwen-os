#!/bin/zsh
cd /Users/jhome/qwenos-work/out/clip_modelpixels/work
for f in "$@"; do ./runsplit.sh $f; done
