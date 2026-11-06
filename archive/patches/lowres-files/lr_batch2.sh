#!/bin/bash
export DMC=/Users/jhome/qwenos-work/wt-lowres/engine/DMC100-Doom
cd /Users/jhome/qwenos-work/wt-lowres
C="-DQ_DUMP_COMPACT"; S="-DQ_RN=15 -DQ_RD=35"; D2="-DQ_DETAIL=2 -DQ_XTVASH=2"
for spec in \
 "b0|" \
 "b1|$C" \
 "c1|$C $S" \
 "c2|$C $S $D2" \
 "c3|$C $S $D2 -DQ_VTOP=60 -DQ_VBOT=200" \
 "c4|$C $S $D2 -DQ_VTOP=60 -DQ_VBOT=200 -DQ_DUMP_ROW2" \
 "c5|$C $S -DQ_VTOP=40 -DQ_VBOT=200" \
 "c6|$C $S -DQ_VTOP=40 -DQ_VBOT=200 -DQ_DUMP_ROW2" \
 "c7|$C $S $D2 -DQ_VTOP=60 -DQ_VBOT=200 -DQ_DUMP_ROW2 -DQ_SOLID" \
 ; do n=${spec%%|*}; f=${spec#*|}
  (cd repo2 && ports/doomdmc/lowres.sh $n "$f" >/dev/null 2>&1); echo "== $n [$f]"; ./lr_run.sh $n
  (cd repo2 && ports/doomdmc/lowres.sh $n "$f" dump >/dev/null 2>&1); echo "== $n-dump"; ./lr_run.sh $n-dump
 done
echo ALLDONE
