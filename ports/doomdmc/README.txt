/bin/doomd = genuine DMC100-Doom engine (GPL-2.0, doomgeneric lineage) on QwenOS RV32IM.
Build:   make build/qwenos-doomdmc.elf   (needs DMC100-Doom checkout + `make gen/nor-images`, see build.sh)
Disk:    NOR image from DMC100 tests/host/mknor.py (E1 pack, FAT12 volumes) served as raw bytes:
         tools/rv32_fast build/qwenos-doomdmc.elf E1.img 100 108 out.bin MAXINSTR [p@FRAME ...]
         (or tools/doomd_ref_run.py for the Python reference CPU). Host = dumb storage only.
Frames:  'p' key arms a serial dump over PUTC; tools/doomd_frames.py out.bin freedoom1.wad prefix -> PNGs.
         The 32x24 kernel framebuffer is also filled (nearest sample) every frame.
Input:   QOS_SYS_KEY_POLL keys (qplat.c dji_tic): w/s fwd/back, a/d turn (menu: up/down/left/right), space or f
         fire (menu: enter), e use, q/r strafe, z run, Esc or m menu, Enter, y/n prompts, . , weapons, Tab map.
         Test-only keys (build with -DQ_NODEBUGKEYS to drop): x exit level, X secret exit, g god, i give all,
         t/T teleport (E1M1), ` print a STATE line. tools/rv32_fast takes -s SCRIPT (frame,key lines), -F maxframes,
         -W disk-out; tools/doomd_play.py + tools/doomd_full_test.py drive scripted playthroughs, PNGs + PASS/FAIL.
Sound:   no device; every I_StartSound emits console bytes 0x03, 0x80|sfx_id (S_sfx index) for a host to play.
Save:    QOS_SYS_DISK_WRITE (21: offset, src, len<=256, completed via DISK_POLL) + qplat.c NOR erase/program on top;
         the image needs a SAVE.DAT (mknor.py --save, 64 KB of 0xFF). Save/Load menu works and survives a restart
         when the host writes the stored bytes back (rv32_fast -W).
Episodes: the disk is up to four 8 MB NOR images, slot k = episode k+1 (tools/mkdisk.py, packs from DMC100's converter,
         see patches/full-engine.patch). The menu shows an episode page when more than one slot is present and the
         main loop re-opens the chosen image (qplat.c q_ep_*). E2M9, E4M2/6/7/9 do not fit the converter's limits.
Overlays are linked straight into ROM (ovl_rv.c); clock is virtual (qplat.c); no USB.
