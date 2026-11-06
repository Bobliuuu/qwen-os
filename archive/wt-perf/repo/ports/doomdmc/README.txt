/bin/doomd = genuine DMC100-Doom engine (GPL-2.0, doomgeneric lineage) on QwenOS RV32IM.
Build:   make build/qwenos-doomdmc.elf   (needs DMC100-Doom checkout + `make gen/nor-images`, see build.sh)
Disk:    NOR image from DMC100 tests/host/mknor.py (E1 pack, FAT12 volumes) served as raw bytes:
         tools/rv32_fast build/qwenos-doomdmc.elf E1.img 100 108 out.bin MAXINSTR [p@FRAME ...]
         (or tools/doomd_ref_run.py for the Python reference CPU). Host = dumb storage only.
Frames:  'p' key arms a serial dump over PUTC; tools/doomd_frames.py out.bin freedoom1.wad prefix -> PNGs.
         The 32x24 kernel framebuffer is also filled (nearest sample) every frame.
Input:   none needed: title loop plays DEMO1 from the image (vanilla demo, real game logic).
Overlays are linked straight into ROM (ovl_rv.c); clock is virtual (qplat.c); no sound/save/USB.
