/bin/doomd = genuine DMC100-Doom engine (GPL-2.0, doomgeneric lineage) on QwenOS RV32IM.
Build:   make build/qwenos-doomdmc.elf   (needs DMC100-Doom checkout + `make gen/nor-images`, see build.sh)
Disk:    NOR image from DMC100 tests/host/mknor.py (E1 pack, FAT12 volumes) served as raw bytes:
         tools/rv32_fast build/qwenos-doomdmc.elf E1.img 100 108 out.bin MAXINSTR [p@FRAME ...]
         (or tools/doomd_ref_run.py for the Python reference CPU). Host = dumb storage only.
Frames:  'p' key arms a serial dump over PUTC; tools/doomd_frames.py out.bin freedoom1.wad prefix -> PNGs.
         The 32x24 kernel framebuffer is also filled (nearest sample) every frame.
Input:   none needed: title loop plays DEMO1 from the image (vanilla demo, real game logic).
Overlays are linked straight into ROM (ovl_rv.c); clock is virtual (qplat.c); no sound/save/USB.
Run modes (compile time; ports/doomdmc/mkmode.sh MODE [FRAMES [DUMP]] -> build/qwenos-doomdmc-m<MODE>[f<FRAMES>][d].elf;
  the default `make build/qwenos-doomdmc.elf` stays mode 0 = attract loop from the title):
  mode 1  DEMO1 straight away (no title/credit pages); the vanilla demo drives the player; exits at its end
  mode 2  E1M1 player start (plan B, textured floors), scripted buttons (q_script in doomd_main.c)
  FRAMES  leave doomd_main after that many game frames (1 = one frame then exit); DUMP=1 sends the last
          frame over PUTC (tools/doomd_frames.py), costs ~3.7M instructions
  Console markers: DOOMD_LEVEL_START <demo1|e1m1>, DOOMD_FRAME n tic t, DOOMD_FRAMES_DONE, DOOMD_DEMO_DONE.
Cost work: -O2 (was -Oz), fastfix.c (FixedDiv via divu, bit-exact), qimg.c (extent run cache, no stats on the
  line-fill path), qsolid.c (repeat plan-D floor/ceiling columns copied), and the main loop skips the redraw of
  a frame that follows no tic (virtual time makes every other TryRunTics call tic-less).
