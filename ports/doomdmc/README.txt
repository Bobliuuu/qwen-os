/bin/doomd = genuine DMC100-Doom engine (GPL-2.0, doomgeneric lineage) on QwenOS RV32IM.
Build:   make build/qwenos-doomdmc.elf   (needs DMC100-Doom checkout + `make gen/nor-images`, see build.sh)
Disk:    NOR image from DMC100 tests/host/mknor.py (E1 pack, FAT12 volumes) served as raw bytes:
         tools/rv32_fast build/qwenos-doomdmc.elf E1.img 3c 44 out.bin MAXINSTR [p@FRAME ...]
         (mailbox addresses = readelf of kernel-doomd.elf: qos_input_mailbox, qos_disk_mailbox;
          LT_ADDR=<hex leveltime> logs the game tic per frame)
         (or tools/doomd_ref_run.py for the Python reference CPU). Host = dumb storage only.
Frames:  'p' key arms a serial dump over PUTC; tools/doomd_frames.py out.bin freedoom1.wad prefix -> PNGs.
         The 32x24 'framebuffer' is no longer resident: samples stream as console packets (FB_COL),
         doomd_frames.py also writes <prefix>-NN-fb32x24.png for each dumped frame.
Input:   none needed: title loop plays DEMO1 from the image (vanilla demo, real game logic).
Overlays are linked straight into ROM (ovl_rv.c); clock is virtual (qplat.c); no sound/save/USB.

RAM squeeze (see RAM_BUDGET.txt here): kernel core 0..0x97, stack 0x480, flats in data ROM, plans A/B
(w16/w8, always textured), record cache 16 B x 16 sets x 4 ways. Build is RAM-layout aware:
  make build/qwenos-doomdmc.elf            engine (patched copies of 4 DMC100 files, ports/doomdmc/dmc-ram.patch;
                                           flats baked by ports/doomdmc/mkflatrom.py from $DMC/build/sw/packs/E1)
  make doomdmc-image DMCWORK=<writable DMC100-Doom copy>   layout JSON (mklayout.py) + repacked E1 pack and
                                           NOR image (mkimage.sh) -> build/doomdmc-pack/E1.img. The image MUST be
                                           repacked: map plans/arenas are baked into it for this exact layout.
