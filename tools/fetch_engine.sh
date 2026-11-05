#!/bin/bash
# Reproducibly fetch + patch DMC100-Doom, fetch Freedoom, convert it and build the NOR disk image (E1.img).
#   tools/fetch_engine.sh            -> .deps/engine/DMC100-Doom (patched, built gen/), .deps/wads/freedoom1.wad,
#                                       .deps/engine/DMC100-Doom/build/sw/nor/E1.img
# env: ENGINE_ROOT (default <repo>/.deps/engine)  WAD (use this freedoom1.wad instead of downloading)
# Needs: git, python3, clang+ld.lld (riscv32), llvm-nm (brew install llvm; on macOS LLVM=/opt/homebrew/opt/llvm/bin), curl, unzip.
# Pinned: DMC100-Doom 0cdc78e + engine-patches/dmc100-qwenos-merged.patch, Freedoom 0.13.0 (freedoom1.wad).
# WARNING: this script builds E1.img with QFLAT_SLOTS=0. That image is NOT the one used for doomd_regress.sh
# (the regress needs the QFLAT_SLOTS image, md5 6287a13cc1079b697e1885f8f6327e06 for the combined build). Do not use this
# E1.img for regress checks; see docs/research/COMBINED.md.
set -e
REPO=$(cd "$(dirname "$0")/.." && pwd)
ENGINE_ROOT=${ENGINE_ROOT:-$REPO/.deps/engine}; DMC=$ENGINE_ROOT/DMC100-Doom
WADDIR=$REPO/.deps/wads; mkdir -p "$ENGINE_ROOT" "$WADDIR"
export LLVM=${LLVM:-/opt/homebrew/opt/llvm/bin}; export PATH=$LLVM:$PATH
if [ ! -d "$DMC/.git" ]; then git clone -q https://github.com/ArturBieniek4/DMC100-Doom "$DMC"; fi
if [ ! -f "$DMC/.qwenos-patched" ]; then
  git -C "$DMC" checkout -q 0cdc78e
  (cd "$DMC" && patch -p1 < "$REPO/engine-patches/dmc100-qwenos-merged.patch" >/dev/null) && touch "$DMC/.qwenos-patched"
fi
if [ -z "$WAD" ]; then
  WAD=$WADDIR/freedoom1.wad
  if [ ! -f "$WAD" ]; then
    curl -fsSL -o "$WADDIR/f.zip" https://github.com/freedoom/freedoom/releases/download/v0.13.0/freedoom-0.13.0.zip
    unzip -oj -q "$WADDIR/f.zip" '*/freedoom1.wad' -d "$WADDIR"
  fi
fi
WAD=$(cd "$(dirname "$WAD")" && pwd)/$(basename "$WAD")
export NM=$REPO/tools/nm_noprefix.sh
IMG=$DMC/build/sw/nor/E1.img
if [ ! -f "$IMG" ]; then
  (cd "$DMC" && make -j8 BUILD=build/sw IWAD="$WAD" gen >/dev/null)
  # layout comes from a doomd link (needs only gen/, not the image), then the converter packs E1 against it
  DMC=$DMC NOBAKE=1 DOOMD_MODE=3 EXTRA_CF="-DDOOMD_FRAMES=0" "$REPO/ports/doomdmc/build.sh" "$REPO/build/doomdmc-layout" >/dev/null
  QFLAT_SLOTS=0 python3 "$REPO/ports/doomdmc/mklayout.py" "$REPO/build/doomdmc-layout/doomd.elf" "$REPO/build/layout.json"
  IWAD="$WAD" "$REPO/ports/doomdmc/mkimage.sh" "$DMC" "$REPO/build/layout.json" "$DMC/build/sw/nor"
fi
echo "WARNING: E1.img above is built with QFLAT_SLOTS=0; do not use it for tools/doomd_regress.sh (see docs/research/COMBINED.md)" >&2
echo "engine: $DMC"; echo "wad:    $WAD"; echo "disk:   $IMG"
