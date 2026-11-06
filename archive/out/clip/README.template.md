# QwenOS DOOM, 3-second clip (E1M1, 45 frames, 15 fps)

Files: `qwenos-doom-3s.mp4` (960x720, H.264 yuv420p, 15 fps, 45 frames = 3.00 s), `qwenos-doom-3s.gif` (480x360, 15 fps),
`qwenos-doom-3s-contact.png` (12 evenly spaced frames), `frames/frame_01..45.png` (native 320x240 decodes),
`frame_instr.json`, `make_clip_ledger.py` (regenerates this README; re-run it as chunks finish).

## Verification status (auto-generated; re-run `python3 make_clip_ledger.py`)

@@SUMMARY@@

Lanes of completed chunks: @@LANES@@.

**Rule used:** a frame is listed "yes" only if every chunk covering it has a `result.json` with `mode: MODEL` and all
segment_detail entries ok=true, no divergence, and a segment range equal to the plan. Anything else is "no".
Frames marked "no" are emulator-only until their chunk result appears.

## What produced it

- Game: Freedoom 1 E1M1 (freedoom1.wad md5 b93be13d05148dd01614bc205a03648e), DMC100-Doom port `/bin/doomd` running on the QwenOS RV32IM kernel, mode 2 (scripted E1M1), FULL preset (160x200 low-detail view, status bar), 15 rendered frames per 35 game tics via skip pattern `floor(t*15/35)` (game logic every tic, skipped tics do not draw).
- Model-verified ELF (final stop-hook build, `make demo-elf`): `build/demo/qwenos-e1m1.elf` md5 `e3eb128286cad572b9951a08b570bcb3` (identical to `build/lr-demo.elf`), chunk-ROM plan `crx-plan.bin` md5 `af843bac13f2cbab6eb2409748209c5d`, disk `E1.img` md5 `6287a13cc1079b697e1885f8f6327e06`. Source tree `wt-validate3/repo` (copy used for pixels: `wt-clip/repo`).
- Model: Qwen3.5-4B merged "rv1" executing the RV32IM trace in lockstep with the oracle (35 chunks, frames 1..45, run plan `out/model/runplan_clip3s.json`: 81,065,587 instructions, 112,762,231 planned chip tokens, 35 chunks, @@NCHUNK@@ chunks completed ok so far with @@TOK@@ chip tokens).
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

@@FRAMETABLE@@

## Chunks (35 planned)

@@CHUNKTABLE@@
