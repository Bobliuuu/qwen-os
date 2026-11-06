# QwenOS DOOM, 3-second clip (E1M1, 45 frames, 15 fps)

Files: `qwenos-doom-3s.mp4` (960x720, H.264 yuv420p, 15 fps, 45 frames = 3.00 s), `qwenos-doom-3s.gif` (480x360, 15 fps),
`qwenos-doom-3s-contact.png` (12 evenly spaced frames), `frames/frame_01..45.png` (native 320x240 decodes),
`frame_instr.json`, `make_clip_ledger.py` (regenerates this README; re-run it as chunks finish).

## Verification status (auto-generated; re-run `python3 make_clip_ledger.py`)

35/35 chunks ok (MODEL), 45/45 frames model-verified, 0 frames emulator-only (chunk pending). Chip tokens in completed chunks: 116,333,007 (plan total 112,762,231); instructions in completed chunks: 81,065,591 of 81,065,587.

Lanes of completed chunks: AWS A10G: 3 chunks, 4209 s model wall; Lambda A100: 3 chunks, 4713 s model wall; Modal A100: 29 chunks, 67477 s model wall.

**Rule used:** a frame is listed "yes" only if every chunk covering it has a `result.json` with `mode: MODEL` and all
segment_detail entries ok=true, no divergence, and a segment range equal to the plan. Anything else is "no".
Frames marked "no" are emulator-only until their chunk result appears.

## What produced it

- Game: Freedoom 1 E1M1 (freedoom1.wad md5 b93be13d05148dd01614bc205a03648e), DMC100-Doom port `/bin/doomd` running on the QwenOS RV32IM kernel, mode 2 (scripted E1M1), FULL preset (160x200 low-detail view, status bar), 15 rendered frames per 35 game tics via skip pattern `floor(t*15/35)` (game logic every tic, skipped tics do not draw).
- Model-verified ELF (final stop-hook build, `make demo-elf`): `build/demo/qwenos-e1m1.elf` md5 `e3eb128286cad572b9951a08b570bcb3` (identical to `build/lr-demo.elf`), chunk-ROM plan `crx-plan.bin` md5 `af843bac13f2cbab6eb2409748209c5d`, disk `E1.img` md5 `6287a13cc1079b697e1885f8f6327e06`. Source tree `wt-validate3/repo` (copy used for pixels: `wt-clip/repo`).
- Model: Qwen3.5-4B merged "rv1" executing the RV32IM trace in lockstep with the oracle (35 chunks, frames 1..45, run plan `out/model/runplan_clip3s.json`: 81,065,587 instructions, 112,762,231 planned chip tokens, 35 chunks, 35 chunks completed ok so far with 116,333,007 chip tokens).
- Pixels: NOT from the model. The model run does not dump pixels. They come from rv32_fast (the C emulator, `build/rv32_fast` md5 `c81a2012acd249755c4902922223ea51`) running the same sources/flags with only the serial dump added: `CHUNKROM=1 TICS=350 ports/doomdmc/lowres.sh demo-dump full dump` -> `build/lr-demo-dump-dump.elf` md5 `5ffd4f94c0225f8e3e2b957d550f6feb` (adds `-DQ_DUMP_ALL`; `-DQ_DUMP_COMPACT` already in the production preset). Run: `CRXPLAN=build/demo/crx-plan.bin CRXBASE=29000 rv32_fast <elf> E1.img 154 15c out.bin 4000000000`; decoded with `tools/lowres_frames.py` (PLAYPAL of the IWAD); frames 1..45 = the first 45 frame markers (marker n = decoded frame index n-1).
- Dump does not change game state (re-verified): QHASH builds (state hash after every tic, lockstep hash of players/sectors/mobjs) with and without `Q_DUMP_ALL` give a byte-identical `TICHASH` stream for all 350 tics (stream md5 29b9691465a7ea771900d9b26ff9956f) and the same 151 frame markers; the dump and production ELFs under the chunk-ROM plan both report GAMETICS n=347, DISK total_req=4, CRX reqs 2/0/0/0/0, 151 frame markers. (The hash builds are separate ELFs because the hash code does not fit the chunk-ROM layout; the production ELF itself carries no hash code.) The dump costs extra instructions (230.8M vs 199.7M total steps for 350 tics), so instruction counts below are from the production ELF run, not the dump run.

## Frame index to game tic, instructions

Frame n = nth frame marker (0x02 console byte). Frame 1 is the first game frame (end of level load, step 3,417,727); the first 3.4M instructions are boot + WAD/level load (the title/boot phase is not drawn into the clip). Later frames come every 2 or 3 game tics (15 of 35). Frame 45 is drawn in game tic 102 (about 2.9 s of game time shown in 3.0 s of video, so playback is real-time speed). Instruction counts per frame (production ELF; sum = 81,065,587, equal to the run plan total) are in the table below.

## Scripted gameplay shown (honest description)

Input is the compiled-in `q_script` (no human input): tics 4-40 forward, 41-50 turn right, 51-70 forward, 71-80 fire, 81+ forward (the 350-tic build continues the script; this clip ends at tic 102). On screen: the player starts in the E1M1 start room facing the hangar, walks forward, turns right, walks down along a long brown/grey wall, fires the pistol (ammo 50 -> 49), and keeps walking along that wall. There is no damage taken (health 100%) and no enemy action; the clip ends running alongside the wall, not facing it.

## Disclosures

- Pixels were rendered by the emulator from the same ELF/state; the Qwen3.5 model verified the instruction trace and the frame-marker bytes in lockstep, not the pixel output. Nothing in the pixel path was executed by the model.
- The disk (E1.img) is host-served through chunk-ROM windows (crx plan boundaries at frames 4, 17, 31): the guest reads disk extents from a host-filled data ROM; only the level load (before frame 1) needs in-run disk requests (2 in chunk 0 through the mailbox, then the plan has zero in-run requests).
- Keyboard input is script-driven (q_script, compiled in, injected by the guest's own input mailbox path) and the clock is virtual (1 ms per idle call), not real time.
- The first frames include level load: frame 1 costs 3.4M instructions (boot + load) versus about 1.1-2.8M for later frames.
- Each chunk starts from a host-supplied snapshot of machine state at its start (host replay), and the model proves the segment from there; chunks ran on different GPU lanes (below).

## Per-frame verification table

| frame | game tic (drawn in) | instr this frame (prod ELF) | chunk(s) | lane | model-verified |
|---:|---:|---:|---|---|---|
| 01 | 0 | 3,417,727 | c00+c01 | Modal A100 | **yes** |
| 02 | 2 | 2,432,636 | c02 | Modal A100 | **yes** |
| 03 | 4 | 2,458,771 | c03 | Modal A100 | **yes** |
| 04 | 6 | 2,437,969 | c04 | Modal A100 | **yes** |
| 05 | 9 | 2,501,405 | c05 | Modal A100 | **yes** |
| 06 | 11 | 2,528,685 | c06 | Modal A100 | **yes** |
| 07 | 13 | 2,596,858 | c07 | Modal A100 | **yes** |
| 08 | 16 | 2,782,065 | c08 | Modal A100 | **yes** |
| 09 | 18 | 2,686,905 | c09 | Modal A100 | **yes** |
| 10 | 20 | 2,264,907 | c10 | Modal A100 | **yes** |
| 11 | 23 | 2,335,547 | c11 | Modal A100 | **yes** |
| 12 | 25 | 2,254,038 | c12 | Modal A100 | **yes** |
| 13 | 27 | 2,148,527 | c13 | Modal A100 | **yes** |
| 14 | 30 | 2,047,702 | c14 | Modal A100 | **yes** |
| 15 | 32 | 2,078,255 | c15 | Modal A100 | **yes** |
| 16 | 34 | 2,176,807 | c16 | Modal A100 | **yes** |
| 17 | 37 | 2,294,193 | c17 | Modal A100 | **yes** |
| 18 | 39 | 2,117,038 | c18 | Modal A100 | **yes** |
| 19 | 41 | 2,036,052 | c19 | Modal A100 | **yes** |
| 20 | 44 | 2,094,260 | c20 | Modal A100 | **yes** |
| 21 | 46 | 1,986,855 | c21 | Modal A100 | **yes** |
| 22 | 48 | 1,864,166 | c22 | Modal A100 | **yes** |
| 23 | 51 | 1,619,091 | c23 | Modal A100 | **yes** |
| 24 | 53 | 1,477,824 | c23 | Modal A100 | **yes** |
| 25 | 55 | 1,415,124 | c24 | Modal A100 | **yes** |
| 26 | 58 | 1,186,718 | c24 | Modal A100 | **yes** |
| 27 | 60 | 1,317,294 | c25 | Modal A100 | **yes** |
| 28 | 62 | 1,066,674 | c25 | Modal A100 | **yes** |
| 29 | 65 | 1,403,779 | c26 | Modal A100 | **yes** |
| 30 | 67 | 1,145,661 | c26 | Modal A100 | **yes** |
| 31 | 69 | 1,215,185 | c27 | Modal A100 | **yes** |
| 32 | 72 | 1,338,415 | c27 | Modal A100 | **yes** |
| 33 | 74 | 1,338,636 | c28 | Modal A100 | **yes** |
| 34 | 76 | 1,607,895 | c28 | Modal A100 | **yes** |
| 35 | 79 | 1,316,671 | c29 | AWS A10G | **yes** |
| 36 | 81 | 1,229,437 | c29 | AWS A10G | **yes** |
| 37 | 83 | 1,323,023 | c30 | Lambda A100 | **yes** |
| 38 | 86 | 1,242,864 | c30 | Lambda A100 | **yes** |
| 39 | 88 | 1,087,764 | c31 | Lambda A100 | **yes** |
| 40 | 90 | 1,226,680 | c31 | Lambda A100 | **yes** |
| 41 | 93 | 1,330,947 | c32 | Lambda A100 | **yes** |
| 42 | 95 | 1,124,058 | c32 | Lambda A100 | **yes** |
| 43 | 97 | 1,104,527 | c33 | AWS A10G | **yes** |
| 44 | 100 | 1,315,244 | c33 | AWS A10G | **yes** |
| 45 | 102 | 1,090,708 | c34 | AWS A10G | **yes** |

## Chunks (35 planned)

| chunk | markers | segment range | instr | chip tokens (model) | lane / host | wall s | result dir | status |
|---|---|---|---:|---:|---|---:|---|---|
| c00 | 0->0 | 1:4 | 1,819,896 | 2,564,928 | Modal A100 (modal) | 2471.1 | chunks/prod1/c00 | ok, MODEL |
| c01 | 0->1 | 4:5 | 1,597,830 | 2,232,547 | Modal A100 (modal) | 1994.3 | chunks/prod1/c01 | ok, MODEL |
| c02 | 1->2 | 5:6 | 2,432,641 | 3,481,364 | Modal A100 (modal) | 5493.0 | chunks/prod1/c02 | ok, MODEL |
| c03 | 2->3 | 6:7 | 2,458,771 | 3,518,372 | Modal A100 (modal) | 4732.6 | chunks/prod1/c03 | ok, MODEL |
| c04 | 3->4 | 7:8 | 2,437,969 | 3,489,392 | Modal A100 (modal) | 2351.7 | chunks/prod1/c04 | ok, MODEL |
| c05 | 4->5 | 8:9 | 2,501,405 | 3,584,517 | Modal A100 (modal) | 4957.5 | chunks/prod1/c05 | ok, MODEL |
| c06 | 5->6 | 9:10 | 2,528,685 | 3,632,609 | Modal A100 (modal) | 2552.2 | chunks/prod1/c06 | ok, MODEL |
| c07 | 6->7 | 10:11 | 2,596,858 | 3,724,842 | Modal A100 (modal) | 4205.7 | chunks/prod1/c07 | ok, MODEL |
| c08 | 7->8 | 11:12 | 2,782,065 | 3,986,282 | Modal A100 (modal) | 6034.9 | chunks/prod1/c08 | ok, MODEL |
| c09 | 8->9 | 12:13 | 2,686,905 | 3,826,544 | Modal A100 (modal) | 5835.4 | chunks/prod1/c09 | ok, MODEL |
| c10 | 9->10 | 13:14 | 2,264,907 | 3,228,958 | Modal A100 (modal) | 2088.7 | chunks/prod1/c10 | ok, MODEL |
| c11 | 10->11 | 14:15 | 2,335,547 | 3,334,059 | Modal A100 (modal) | 1350.8 | chunks/prod1p/c11 (+1 duplicate run) | ok, MODEL |
| c12 | 11->12 | 15:16 | 2,254,038 | 3,225,633 | Modal A100 (modal) | 1249.6 | chunks/prod1p/c12 (+1 duplicate run) | ok, MODEL |
| c13 | 12->13 | 16:17 | 2,148,527 | 3,080,501 | Modal A100 (modal) | 1195.6 | chunks/prod1p/c13 (+1 duplicate run) | ok, MODEL |
| c14 | 13->14 | 17:18 | 2,047,702 | 2,950,102 | Modal A100 (modal) | 1143.9 | chunks/prod1p/c14 | ok, MODEL |
| c15 | 14->15 | 18:19 | 2,078,255 | 2,990,224 | Modal A100 (modal) | 1247.6 | chunks/prod1p/c15 | ok, MODEL |
| c16 | 15->16 | 19:20 | 2,176,807 | 3,111,636 | Modal A100 (modal) | 1299.2 | chunks/prod1p/c16 | ok, MODEL |
| c17 | 16->17 | 20:21 | 2,294,193 | 3,260,708 | Modal A100 (modal) | 1392.6 | chunks/prod1p/c17 | ok, MODEL |
| c18 | 17->18 | 21:22 | 2,117,038 | 3,035,715 | Modal A100 (modal) | 1443.0 | chunks/prod1p/c18 | ok, MODEL |
| c19 | 18->19 | 22:23 | 2,036,052 | 2,947,021 | Modal A100 (modal) | 1246.1 | chunks/prod1p/c19 | ok, MODEL |
| c20 | 19->20 | 23:24 | 2,094,260 | 3,018,532 | Modal A100 (modal) | 1285.8 | chunks/prod1p/c20 | ok, MODEL |
| c21 | 20->21 | 24:25 | 1,986,855 | 2,860,493 | Modal A100 (modal) | 1231.4 | chunks/prod1p/c21 | ok, MODEL |
| c22 | 21->22 | 25:26 | 1,864,166 | 2,688,213 | Modal A100 (modal) | 1165.8 | chunks/prod1p/c22 | ok, MODEL |
| c23 | 22->24 | 26:27 | 3,096,915 | 4,460,668 | Modal A100 (modal) | 1984.7 | chunks/prod1p/c23 | ok, MODEL |
| c24 | 24->26 | 27:28 | 2,601,842 | 3,770,019 | Modal A100 (modal) | 1463.6 | chunks/prod1p/c24 | ok, MODEL |
| c25 | 26->28 | 28:29 | 2,383,968 | 3,476,165 | Modal A100 (modal) | 1394.9 | chunks/prod1p/c25 | ok, MODEL |
| c26 | 28->30 | 29:30 | 2,549,440 | 3,702,596 | Modal A100 (modal) | 1457.0 | chunks/prod1p/c26 | ok, MODEL |
| c27 | 30->32 | 30:32 | 2,553,600 | 3,677,006 | Modal A100 (modal) | 1469.9 | chunks/prod1p/c27 | ok, MODEL |
| c28 | 32->34 | 32:33 | 2,946,531 | 4,205,280 | Modal A100 (modal) | 1738.2 | chunks/prod1p/c28 | ok, MODEL |
| c29 | 34->36 | 33:34 | 2,546,108 | 3,660,576 | AWS A10G (ip-172-31-17-25) | 1755.7 | chunks/c29 | ok, MODEL |
| c30 | 36->38 | 34:35 | 2,565,887 | 3,686,177 | Lambda A100 (129-146-78-123) | 1641.3 | chunks/c30 | ok, MODEL |
| c31 | 38->40 | 35:36 | 2,314,444 | 3,344,358 | Lambda A100 (129-146-78-123) | 1495.5 | chunks/c31 | ok, MODEL |
| c32 | 40->42 | 36:37 | 2,455,005 | 3,524,411 | Lambda A100 (129-146-78-123) | 1576.0 | chunks/c32 | ok, MODEL |
| c33 | 42->44 | 37:38 | 2,419,771 | 3,476,641 | AWS A10G (ip-172-31-17-25) | 1678.0 | chunks/c33 | ok, MODEL |
| c34 | 44->45 | 38:39 | 1,090,708 | 1,575,918 | AWS A10G (ip-172-31-17-25) | 775.0 | chunks/c34 | ok, MODEL |
