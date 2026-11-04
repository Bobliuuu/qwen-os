# 07 DMC100-Doom port to RV32IM

Goal: run a genuine GPL DOOM-derived engine as `/bin/doomd`.

Method: take ArturBieniek4/DMC100-Doom (STM32/Thumb, 42 KB execute-from-RAM overlays, preconverted `DOOM.DAT` assets on NOR). Rebuild with clang riscv32; link the overlays straight into ROM (`ports/doomdmc/ovl_rv.c`); platform layer `qplat.c` (virtual clock, NOR reads over the QwenOS disk mailbox, no USB/sound/save at first), `qlcd.c` (frame output), `doomd_main.c`, `rtlib.c`, `build.sh`. Disk = NOR image from DMC100's `tests/host/mknor.py` served as raw bytes. Frames out via a serial dump over PUTC (`tools/doomd_frames.py`). Run modes (`mkmode.sh`): 0 attract loop, 1 DEMO1, 2 E1M1 scripted.

Numbers (agent report unless noted): text about 146 KB, rodata about 29 KB. First DEMO1 frame 11.26 M instructions, about 3.5 M per tic. (Frames `out/doomd-demo1-0*.png`.) Disk requests were thousands per frame (the model-run docstring quotes 3.8-5.8 k requests and 140-160 KB unique data per later frame).
Result: worked; DEMO1 plays real game logic on the emulator.
Files: `ports/doomdmc/*`, `tools/doomd_frames.py`, `tools/doomd_ref_run.py`, `tools/rv32_fast.c`, `Makefile`.
Reproduce: `make build/qwenos-doomdmc.elf` needs a DMC100-Doom checkout and `make gen/nor-images` (build.sh, env `DMC`).
Evidence: TRACES/frames/02_dmc_demo1_frame.png. Note first-frame instruction counts differ by build, see table in 08.
