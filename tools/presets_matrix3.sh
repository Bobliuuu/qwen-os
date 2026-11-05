#!/bin/bash
# Third matrix (15 fps kept): lite candidates and Q_SOLID / Q_STRIPW. Output: build/pm/matrix3.txt
cd "$(dirname "$0")/.."
mkdir -p build/pm
SK="-DQ_DUMP_COMPACT"
R15="-DQ_RN=15 -DQ_RD=35"
D2="-DQ_DETAIL=2 -DQ_XTVASH=2"
LB="-DQ_VTOP=40 -DQ_VBOT=200"
run() { tools/presets_measure.sh "$1" "$SK $2" > build/pm/$1.sum 2>&1; }
run e_lite "$R15 $LB -DQ_NOBAR -DQ_FIXEDLIGHT=0" & run e_solid "$R15 -DQ_SOLID=1" & run e_fastsolid "$R15 $D2 $LB -DQ_NOBAR -DQ_FIXEDLIGHT=0 -DQ_SOLID=1" \
  & run e_d2nobar "$R15 $D2 -DQ_NOBAR -DQ_FIXEDLIGHT=0" & wait
cat build/pm/e_*.sum > build/pm/matrix3.txt
