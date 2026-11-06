#!/bin/bash
# watches ./snaps/segN.pkl (written atomically by the dump pass) and uploads each to Modal volume qwenos-snaps
export PATH=$HOME/.pyenv/shims:$PATH; cd /Users/jhome/qwenos-work/out/model
mkdir -p snaps_done
while true; do
  for f in snaps/seg*.pkl; do [ -f "$f" ] || continue; b=$(basename $f)
    [ -f snaps_done/$b ] && continue
    modal volume put -f qwenos-snaps $f /$b >/dev/null 2>&1 && touch snaps_done/$b && echo "up $b $(date +%T)"
  done
  grep -q DUMP_DONE dump_local.log && [ $(ls snaps/seg*.pkl | wc -l) -eq $(ls snaps_done | wc -l) ] && { echo UPLOAD_DONE; break; }
  sleep 3
done
