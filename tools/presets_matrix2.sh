#!/bin/bash
# Second matrix: combined candidates. Output: build/pm/matrix2.txt
cd "$(dirname "$0")/.."
mkdir -p build/pm
SK="-DQ_DUMP_COMPACT"
R15="-DQ_RN=15 -DQ_RD=35"
D2="-DQ_DETAIL=2 -DQ_XTVASH=2"
LB="-DQ_VTOP=40 -DQ_VBOT=200"
run() { tools/presets_measure.sh "$1" "$SK $2" > build/pm/$1.sum 2>&1; }
run c_fast "$R15 $D2 $LB -DQ_NOBAR" & run c_fastL "$R15 $D2 $LB -DQ_NOBAR -DQ_FIXEDLIGHT=0" \
  & run c_ultra "-DQ_RN=15 -DQ_RD=70 $D2 $LB -DQ_NOBAR -DQ_FIXEDLIGHT=0" & run c_ultra10 "-DQ_RN=10 -DQ_RD=35 $D2 $LB -DQ_NOBAR -DQ_FIXEDLIGHT=0" & wait
cat build/pm/c_*.sum > build/pm/matrix2.txt
# frame dumps for PNGs (100 tics)
dump() { TICS=100 ports/doomdmc/lowres.sh "d-$1" "$SK $2" dump >/dev/null; }
dump full "$R15" & dump det2 "$R15 $D2" & dump lbox "$R15 $LB" & dump nobar "$R15 -DQ_NOBAR" \
  & dump flight0 "$R15 -DQ_FIXEDLIGHT=0" & dump fast "$R15 $D2 $LB -DQ_NOBAR" & dump fastL "$R15 $D2 $LB -DQ_NOBAR -DQ_FIXEDLIGHT=0" & dump max "$R15 $D2 $LB" & wait
