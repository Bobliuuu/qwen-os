#!/usr/bin/env python3
"""Builds the QwenOS DOOM disk: one 8 MB NOR image per episode (slot k = episode k+1), each with a blank
SAVE.DAT, concatenated. usage: mkdisk.py PACKS_DIR OUT.img [episodes e.g. 1234]
PACKS_DIR holds E1.. (converter output, `tools/conv --packs E1,E2,E3,E4`), MKNOR is DMC100's tests/host/mknor.py."""
import os, subprocess, sys, tempfile
packs, out = sys.argv[1], sys.argv[2]
eps = sys.argv[3] if len(sys.argv) > 3 else "1234"
mknor = os.environ.get("MKNOR", "/Users/jhome/qwenos-work/engine/DMC100-Doom/tests/host/mknor.py")
with tempfile.TemporaryDirectory() as t:
    blank = os.path.join(t, "save.blank"); open(blank, "wb").write(b"\xff" * 65536)
    with open(out, "wb") as f:
        for e in eps:
            img = os.path.join(t, "e%s.img" % e)
            subprocess.check_call([sys.executable, mknor, os.path.join(packs, "E" + e), img, "--save", blank, "--nor-mb", "8"])
            f.write(open(img, "rb").read())
