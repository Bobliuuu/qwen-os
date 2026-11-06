# 19 Emulator gameplay video (tier T0)

Goal: a demonstration clip of the game running.
Result: `out/video/qwenos-doom-e1m1.mp4`: 30.29 s, 1060 frames, 960x720 (3x nearest of 320x240), 35 fps, md5 e53d874d97cd9a87d102be0100d6f6a9 (6.3 MB); `.gif` 320x240 about 11.67 fps (md5 cc156484...). Not copied (size). Built from `doomd-m2-dumpall.elf` (md5 5030876bcc952c92cb04d1cbdeea26a7, 255 KB, only in `out/video/`) with disk E1.img (md5 79b7d86efb58c3078d035a6736e38e3f), WAD freedoom1 (md5 b93be13d05148dd01614bc205a03648e).
Method: mode 2 (E1M1, skill 3), `-DQ_DUMP_ALL -DQ_KEYSONLY`, route file `e1m1_route.keys` (TRACES/video), command in REPRODUCE.md. One uninterrupted T0 run.
Numbers (measured, FRAMELOG): 5,457,271,471 instr total; frame 0 at 9,058,901; per tic over frames 1..1059 mean 5.14 M, median 5.24 M, min 3.72 M, max 9.03 M (includes serial dump); about 250 M instr/s, 21.9 s CPU.
Debug keys: T teleport at tic 441 (visible cut), g god mode at tic 653 (earlier take: imps killed the player near tic 940). Tics 2..440 use real keys only, so the first 10 s (tics 2..350) is replayable by a model run unchanged.
Gaps: all 1060 frames are T0 only; not T1 lockstep-checked, not model-verified. Decoder `tools/doomd_video.py` exists only in `wt-video` (not byte-compared with `doomd_frames.py`). `wt-video.diff` (48 KB) holds the code delta vs the main repo; kernel DISK_WRITE hunk applied but the kernel ELF not rebuilt; keyboard hunks of qplat.c re-applied by hand because the patch no longer applied to the perf-updated tree.
Evidence: TRACES/video/VIDEO_README.md, TRACES/video/e1m1_route.keys, PROVENANCE.md "Appended by video agent".
