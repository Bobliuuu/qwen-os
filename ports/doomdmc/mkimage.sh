#!/bin/bash
# usage: mkimage.sh DMC_WORKCOPY LAYOUT.json OUTDIR   -> OUTDIR/E1/{DOOM.DAT,..}, OUTDIR/E1.img
# DMC_WORKCOPY must be a writable DMC100-Doom checkout (the converter builds its host dumper in
# its build/ dir). IWAD defaults to .deps/wads/freedoom1.wad.
set -e
DMC=$1; LAY=$2; OUT=$3; IWAD=${IWAD:-.deps/wads/freedoom1.wad}
LLVM=${LLVM:-/opt/homebrew/opt/llvm/bin}; export PATH=$LLVM:$PATH
W=$(mktemp -d); printf '#!/bin/bash\nllvm-nm "$@" | sed -E "s/^_//"\n' > $W/nm; chmod +x $W/nm   # macOS: strip the _ prefix
mkdir -p "$OUT"
cd "$DMC"
NM=$W/nm python3 -I tools/conv/__main__.py --wad "$IWAD" --gen "${GEN:-build/sw/gen}" --packs E1 --out "$OUT" --ram-layout "$LAY" packs | grep '^pack'
python3 -I tests/host/mknor.py "$OUT/E1" "$OUT/E1.img"
rm -rf $W
