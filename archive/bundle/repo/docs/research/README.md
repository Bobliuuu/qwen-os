# QwenOS runs DOOM inside Qwenputer: research record

Date of record: 2026-11-03/04. Written from the agent work trees under `/Users/jhome/qwenos-work`
(`patches/`, `out/`, `engine/`, `wt-*`) and the upstream Qwenputer checkout. Where a number comes
only from an agent report and could not be re-derived from a file, the text says "agent report".

Goal of the effort: run a real DOOM engine as an application of QwenOS (an RV32IM OS) on the RV32IM
CPU that Qwenputer compiles into Qwen3.5 transformer layers, and show gameplay frames whose
instruction trace the model actually executed.

## Contents

| File | What it is |
|---|---|
| [STATUS.md](STATUS.md) | Live status; section for the final merged build and the 5 s clip (both `pending`) |
| [TIMELINE.md](TIMELINE.md) | Chronological narrative of every attempt |
| [HONESTY.md](HONESTY.md) | Exactly what is and is not claimed |
| [REPRODUCE.md](REPRODUCE.md) | Commands for build, regress, emulator, upstream, model, live demo (verified/unverified marked) |
| [experiments/](experiments/) | One file per experiment or patch (index below) |
| [TRACES/](TRACES/README.md) | Small evidence files: run JSONs, ledger, results, request analyses, 15 frames, patches with md5 |

## Executive summary

1. QwenOS (v0.11 starting point: kernel, shell, WAD map viewer, RV32 emulator) was extended until a genuine
   DOOM engine (DMC100-Doom, GPL-2.0, doomgeneric lineage, 32 KB-RAM port) runs as `/bin/doomd` on
   the Qwenputer memory map (32 KiB RAM, 128 KiB data ROM, 256 KiB exec ROM, no execute-from-RAM).
2. On the C emulator (tier T0) the game works end to end: title/menu, 4 episodes (E1 9/9, E2 8/9, E3 8 played of 9
   packed, E4 5 of 9 maps packed), keyboard, doors, pickups, damage, saves (host-written), sound events as console
   bytes, and a 30.29 s, 1060-frame scripted E1M1 video. Measured cost: about 5.1 M guest instructions per
   rendered E1M1 tic at 320x240 with the full serial dump, about 1.3 M mean per game tic in the low-res/skip
   configurations (different metrics, see experiments 09 and 14).
3. Instruction cost per game tic was cut from 10.47 M to 3.52 M mean (perf.patch, agent report), with
   further reductions from syscall squeeze (-7 %), renderer work (-18 %), frame skip (-52 % total instructions at
   15/35) and disk-request removal (bake: -95 % requests; chunk ROM: 165,054 -> 4 requests for +6.6 % instructions).
4. On the real Qwen model (tier T2, merged Qwen3.5-4B "rv1", A100-SXM4-40GB) four runs passed with a lockstep oracle and zero
   divergence: probe, title-frame (6,563 instr), and cold boot to the first frame marker
   (1,552,382 instr, 2,091,327 chip tokens, 292 segments, 1,438 s). No gameplay (E1M1) frame has been executed by the model.
5. The model is slow for this workload: measured 1,454 chip tokens/s end to end (about 1,080 instr/s) on an A100
   against the upstream README claim of about 3,700 instr/s for a compact executor on an L4. A first E1M1 frame is
   5.84 M instr (about 7.9 M chip tokens); 150 frames at 15 fps is about 227 M instr (about 305 M tokens, derived).
6. Every demonstration frame to date comes from the emulator. The merge of all patches into one build is in progress
   (`/Users/jhome/qwenos-work/wt-merge`); its regression run currently fails one check (see STATUS.md).

## Honest status table: what runs where

Tiers: T0 = C emulator `tools/rv32_fast`; T1 = upstream Python reference CPU (`chipformer.rv.ref.Machine`) or
our Python reference; T2 = real Qwen model with lockstep oracle. "Verified" for T2 means every chip token matched the oracle.

| Item | T0 emulator | T1 upstream reference | T2 Qwen model | Evidence |
|---|---|---|---|---|
| QwenOS kernel boot + shell + WAD viewer | yes (`make check`, 29-35 tests) | yes: 120,267 instr, about 173 k chip tokens, `QWENOS_BOOT_OK` (README, no log file kept) | no (probe only) | repo README |
| Model probe (park/resume ABI) | yes | yes | yes, 140 chip tokens, 57 text, no divergence | PROVENANCE 5b |
| Title-frame, 6,563 instr | yes | yes (host prerun) | yes, 9,999 chip tokens, 55 s | TRACES/model/title.json |
| Cold boot to first frame marker (title picture) | yes | yes (truth machine) | yes: 1,552,382 instr, 2,091,327 tokens, 292 segments, 1,438 s | TRACES/model/boot.json |
| DOOM E1M1 gameplay frames | yes, 1060 frames | partial: lockstep to 2.5 M instr in regress test; dry-run plans to 12 M instr | no | video README, regress |
| DEMO1 (vanilla demo, 256 unique frames) | yes, golden hashes | lockstep checkpoints only | no | tests/golden |
| 4 episodes, saves, intermissions | yes | no | no | TRACES/full/results.txt |
| Interactive typed-key live shell | yes (`qwenos_live.sh`) | key schedule helper only | no | experiment 15 |
| Disk (WAD data) | host-served block device in every tier | same | host-served between segments | HONESTY.md |

Frames model-verified in total: 1 (the boot frame marker; the pixels of that frame are the title picture drawn by the guest).
Frames model-verified from actual gameplay: 0.

## Experiment index

| # | Experiment | Result |
|---|---|---|
| 01 | [v0.11 starting state](experiments/01-v011-starting-state.md) | baseline |
| 02 | [Real-WAD BSP viewer (Freedoom)](experiments/02-bsp-viewer-freedoom.md) | worked, not DOOM |
| 03 | [Upstream reference CPU verification](experiments/03-upstream-reference-cpu.md) | worked |
| 04 | [doomgeneric feasibility](experiments/04-doomgeneric-feasibility.md) | RAM no-go; led to DMC100 |
| 05 | [Qwenputer audit](experiments/05-qwenputer-audit.md) | constraints; two ideas rejected |
| 06 | [Kernel RAM reclaim / takeover](experiments/06-kernel-ram-reclaim.md) | worked |
| 07 | [DMC100 port to RV32](experiments/07-dmc100-port.md) | worked |
| 08 | [Floors, E1M1, redraw skip, -O2, fastfix](experiments/08-floors-e1m1-redraw-skip.md) | worked |
| 09 | [Instruction optimization (perf.patch)](experiments/09-perf-instruction-optimization.md) | worked |
| 10 | [Syscall squeeze (sys.patch)](experiments/10-sys-syscall-squeeze.md) | worked |
| 11 | [Renderer (render.patch)](experiments/11-render.md) | worked |
| 12 | [RAM squeeze (ram.patch)](experiments/12-ram-squeeze.md) | worked |
| 13 | [Full-game work (full.patch)](experiments/13-full-game.md) | worked with limits |
| 14 | [Low-res and frame-skip presets](experiments/14-lowres-frameskip.md) | worked; 80-col rejected for the video |
| 15 | [OS flow / live shell](experiments/15-os-flow.md) | worked |
| 16 | [Test and regression (test.patch)](experiments/16-test-regression.md) | worked; found a real bug |
| 17 | [Bake](experiments/17-bake.md) | worked; shelved for chunk ROM |
| 18 | [Chunk ROM](experiments/18-chunk-rom.md) | worked on host; not yet run on the model |
| 19 | [Emulator gameplay video](experiments/19-emulator-video.md) | done, T0 only |
| 20 | [Model runs on the A100](experiments/20-model-runs-a100.md) | probe/title/boot passed; no gameplay |
| 21 | [Fleet prep on AWS](experiments/21-fleet-prep.md) | launched, no results recorded |
| 99 | [Dead ends and open gaps](experiments/99-dead-ends-and-open-gaps.md) | |
