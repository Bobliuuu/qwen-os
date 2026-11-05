#!/bin/bash
# Exploration matrix for docs/research/PRESETS.md (parallel builds+runs). Output: build/pm/matrix.txt
cd "$(dirname "$0")/.."
mkdir -p build/pm
SK="-DQ_DUMP_COMPACT"
R15="-DQ_RN=15 -DQ_RD=35"
D2="-DQ_DETAIL=2 -DQ_XTVASH=2"
LB="-DQ_VTOP=40 -DQ_VBOT=200"
run() { tools/presets_measure.sh "$1" "$SK $2" > build/pm/$1.sum 2>&1; }
run full "$R15" & run nodraw "-DQ_RN=1 -DQ_RD=1" & run fps10 "-DQ_RN=10 -DQ_RD=35" & run fps75 "-DQ_RN=15 -DQ_RD=70" & wait
run fps5 "-DQ_RN=5 -DQ_RD=35" & run det2 "$R15 $D2" & run lbox "$R15 $LB" & run nobar "$R15 -DQ_NOBAR" & wait
run flight0 "$R15 -DQ_FIXEDLIGHT=0" & run flight16 "$R15 -DQ_FIXEDLIGHT=16" & run max "$R15 $D2 $LB" & run det0 "$R15 -DQ_DETAIL=0" & wait
cat build/pm/*.sum > build/pm/matrix.txt
