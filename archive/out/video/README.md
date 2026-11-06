# QwenOS /bin/doomd E1M1 gameplay video

File: `qwenos-doom-e1m1.mp4` (960x720 = 3x nearest-neighbour of 320x240, H.264 yuv420p, 35 fps, 1060 frames, 30.29 s, ~6.3 MB). Also `qwenos-doom-e1m1.gif` (320x240, 11.67 fps = every 3rd frame, ~7 MB).
mp4 md5 e53d874d97cd9a87d102be0100d6f6a9.

## What produced it (tier T0, NOT the Qwen model)
- Real DMC100-Doom engine (GPL, doomgeneric lineage) on Freedoom Phase 1 data, running as QwenOS `/bin/doomd` (RV32IM, ROM-linked).
- Executed by the C RV32IM emulator `tools/rv32_fast` (T0). No Qwen model, no GPU, no T1/T2 involved. Every pixel and every game tic in this video comes from the emulator. These frames are emulator frames, not model-run frames.
- ELF: `doomd-m2-dumpall.elf` (full QwenOS image `build/qwenos-doomdmc-m2.elf`, built with `ports/doomdmc/mkmode.sh 2` + `XCF="-DQ_DUMP_ALL -DQ_KEYSONLY"`), md5 5030876bcc952c92cb04d1cbdeea26a7.
- Disk image (NOR, E1 pack): `out/full/img/E1.img` md5 79b7d86efb58c3078d035a6736e38e3f. WAD for palette: `wads/freedoom1.wad` md5 b93be13d05148dd01614bc205a03648e (real PLAYPAL, palette number taken per frame from the guest dump, so damage/pickup flashes are real).
- Command: `FRAMELOG=1 build/rv32_fast build/qwenos-doomdmc-m2.elf E1.img 100 108 out.bin 40000000000 -s e1m1_route.keys -F 1060`, then `tools/doomd_video.py out.bin freedoom1.wad out.mp4` (numpy decoder of the same 0x01 P/W/D/E serial dump format as `tools/doomd_frames.py`; same PLAYPAL mapping; not byte-compared against doomd_frames.py output).
- Mode 2 = E1M1 start, skill 3 (sk_medium, "hurt me plenty"), no title/menu/sound. Built-in mode-2 button script disabled (Q_KEYSONLY), all input is the key route below, injected by the host through the QOS key mailbox (one key per tic, round-robin among simultaneously held keys; each press is held 120 virtual ms by the guest).
- Q_DUMP_ALL: guest sends a frame-end marker and the changed columns for every game tic (full status band on frame 0 only; host canvas keeps unchanged pixels). 1060 frames == 1060 game tics == 30.29 s of game time at 35 tics/s. Clock is virtual.

## Instruction counts (measured, FRAMELOG)
- Total 5,457,271,471 guest instructions for 1060 frames (frame 0 reached at 9,058,901 instr: boot, image init, level load).
- Per tic (frames 1..1059, instruction delta between frame markers): mean 5.14M, median 5.24M, min 3.72M, max 9.03M; total 5,448,212,570.
- Emulator wall time 21.9 s user (~250M instr/s); 1:14 wall on a heavily loaded machine.

## Key route (also `e1m1_route.keys`, rv32_fast `-s` format "first[-last] key", frame == tic)
Frame k is the k-th 0x02 marker; a key range is re-injected every frame in it. Source: `tools/e1m1_route.py` in the work copy. A STATE probe key (`) every 100 frames is also in the keys file; it only prints to the console.
| tics | key | action |
|---|---|---|
| 2-52 | w | walk east from the start through the gate |
| 53-190 | space | fire pistol at two former humans (real kills 1,2) |
| 100-112 / 125-137 | q / r | strafe left / right |
| 191-239 | w + z | walk/run to corridor end, bonus + clip pickups |
| 240-262 | d | turn right ~120 degrees |
| 263-420 | space (+q 290-300, r 320-332, q 350-360) | fire at the next monster, dodge |
| 421-440 | w | walk back |
| 441 | T | DEBUG KEY: teleport to the corridor in front of the shotgun-shell door (cut in the video, around 12.6 s) |
| 452-454 | e | use: door opens |
| 480-506 | w | into the dark room, pick up box of shotgun shells |
| 507-540 | d | turn ~180 degrees |
| 541-636 | w | back out |
| 637-651 | a | turn left |
| 652-700 | w | out into the green courtyard |
| 653 | g | DEBUG KEY: god mode (without it imps killed the player at ~tic 940 in an earlier take; final HUD health stays 66-67%) |
| 701-711 | a | turn toward the barrels |
| 712-790 | space | pistol fires; an explosive barrel blows up at ~tic 790 |
| 791-850 | w | walk on into the building |
| 851-865 | a | turn left |
| 866-940 | w | walk, "Got the pump-action shotgun" |
| 941-1060 | space | fire (shotgun) |
Replay for a model run: the first N tics of this file are self-contained from boot (e.g. 10 s of game = tics 2..350, or 150 rendered frames at 15 fps = first ~350 tics sampled every ~2.33; the route up to tic 350 uses only real keys w,space,q,r,z,d).

## Honest gaps
- This is T0 only. Nothing here is model-verified.
- Two debug keys are used: `T` teleport at tic 441 (visible discontinuity) and `g` god mode at tic 653. Everything before tic 441 is real walking/shooting with no debug keys.
- Real movement/fights, but monsters are the stock Freedoom E1M1 placement; the shot sequence depends on emulator determinism (virtual clock), so it reproduces exactly on rv32_fast.
- Kernel-side `QOS_SYS_DISK_WRITE`/savegame piece of full.patch was applied to kernel/main.c and include/qos.h in the work copy, but the kernel ELF was not rebuilt and sound/save hunks of qplat.c/build.sh were skipped (not needed). Keyboard hunks of qplat.c were re-applied by hand because the patch no longer applied to the perf-updated tree.
- Early frames before the player is fully in view of the level look correct; no frames from the title/menu are included.
- Code changes (diff vs bundle/repo): `wt-video.diff` here; working tree `/Users/jhome/qwenos-work/wt-video` (uncommitted).
