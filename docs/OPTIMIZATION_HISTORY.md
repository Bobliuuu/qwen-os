# Optimization history and earlier steps

Moved out of the README (verbatim) so the front page shows only the current state. Current numbers are in the README and in the ledgers under `docs/`.

## What we fixed since the first clip

### 🛠️ What we fixed since the first clip

- Before, every instruction of the clip was verified, but **the emulator read the pixels out of memory**. Now the **model emits the pixels**, each byte lockstep-checked.
- Before, the typed flow had not been run on the model. Now `boot -> help, ls, run /bin/doomd -> first DOOM frame marker and two more (markers 2 and 3)` is **model-verified** (4 Modal A100 chunks, 8,239,190 instructions, about 11.7 M chip tokens, 27 segments, zero divergence; keys arrive at `qos_key_park` via the key ring; [details](docs/research/TYPED_FLOW_MODEL.md)).
- Before, it ran at about 1.7 k instr/s. Now it is about **2x faster on the model** (block verification plus fused kernels, bit-exact, see below).
- Before, the older build was used. The tuned build executes fewer instructions (-10.8 % on the clip, host emulator). The tuned build has **not** been re-verified over the whole clip.

## Keyboard: before and now

**Before and now.** The 3-second clip never used the key ring: its input was a script compiled into the game, and the typed boot-to-DOOM flow had not been run on the model. Now the typed flow has:

<p align="center"><img src="docs/assets/keyboard-before-after.gif" alt="Animated before and now: scripted input (q_script) for the 3-second clip versus typed keys through the key ring, help, ls and run /bin/doomd, verified on the model" width="100%"><br><sub>Animated SVG version: <a href="docs/assets/keyboard-before-after.svg">docs/assets/keyboard-before-after.svg</a></sub></p>

## 📉 How much we pushed down, in total

<p align="center"><img src="docs/assets/total-reduction.gif" alt="Animated before and after bars: instructions per tic 10.47 M to 0.43 M, disk pauses 165,054 to 4, model speed 1,100 to 3,562 instructions per second, time per frame 27 to 7.5 minutes" width="100%"><br><sub>Animated SVG version: <a href="docs/assets/total-reduction.svg">docs/assets/total-reduction.svg</a></sub></p>

From the first working DOOM port to now, across the instruction count, the disk traffic, the model's speed and the time per frame:

| What | Before | Now | Change | How we know |
|---|---|---|---|---|
| 🎲 Instructions per game tic (mean) | 10.47 M (first profiled E1M1 build) | 0.43 M (150.16 M over 350 tics) | **about 24x fewer** | host emulator; includes visual choices (drawing 15 of 35 tics for 15 fps, the 160x200 FULL preset) |
| 🧮 Of that, the exact cuts only (same picture) | 180.55 M per 350 tics | 150.16 M | **-16.8%** instructions, -19.4% chip tokens | host emulator, hashes identical to the goldens |
| 💽 Disk pauses (350 tics) | 165,054 | 4 | **-99.998%** | host emulator; costs about 10% more instructions (180.5 M to 199.7 M on the original build) |
| 🎞️ The 3-second clip (45 frames) | 81.07 M instructions | 72.28 M | **-10.8%** | host emulator, published build vs combined build |
| ⚡ Model speed, A100 | about 1,100 instr/s (672 with the original driver) | 3,562 instr/s | **3.2x** (5.3x vs the original driver) | measured, lockstep on, boot chunk |
| 🪙 Chip tokens per second | 1,454 | 5,050 | **3.5x** | measured, different chunks |
| 🔧 GPU time per token | 242 µs | 162 µs | **-33%** | measured microbench, A100, bit-exact kernels |
| ⏱️ Time per game tic on the model | about 7.4 min | about 2.0 min | **3.7x faster** | derived from the rows above |
| 🖼️ Time per displayed frame on the model | about 27 min (45 min with the original driver) | about 7.5 min | **3.6x faster** (6x vs the original driver) | projection from measured chunk speeds |
| 🏁 Gap to real time (15 fps = 0.067 s per frame) | about 24,000x (40,000x originally) | about 6,700x | | projection |

How the first row came about: the early build (DEMO1/E1M1, one draw per tic) cost 10.47 M instructions per tic; caches and inline disk reads took that to 3.52 M, then the render, syscall and RAM patches, flat floors and low detail, and finally drawing 15 of 35 tics brought the mean to about 0.5 M. Drawing every tic would still cost 979 k per tic, about twice the 15 fps mean. The second row is the part that is exact, with an identical picture. Details: [`HISTORY.md`](docs/HISTORY.md), [`TIMELINE.md`](docs/research/TIMELINE.md), [`COMPILER_BENCH.md`](docs/research/COMPILER_BENCH.md), [`HOTLOOPS.md`](docs/research/HOTLOOPS.md), [`COMBINED.md`](docs/research/COMBINED.md), [`PRESETS.md`](docs/research/PRESETS.md).

<details>
<summary><b>📉 The exact instruction cuts, step by step</b></summary>

<p align="center"><img src="docs/assets/instruction-diet.gif" alt="Animated bars: instructions per 350 DOOM tics fall from 180.6 M to 150.2 M, down 16.8 percent" width="100%"></p>

| Step | Instructions | Chip tokens | vs the original build |
|---|---|---|---|
| Original build (-O2) | 180.55 M | 259.04 M | baseline |
| + LTO, Zba, hot code at -O3 | 164.51 M | 238.22 M | -8.9% instructions, -8.0% tokens |
| + wall columns drawn in word runs | 152.01 M | 211.24 M | -15.8%, -18.4% |
| + faster `memcpy`/`memset` and `FixedDiv` (combined) | 150.16 M | 208.78 M | -16.8%, -19.4% |

Tokens fall more than instructions because a word store costs 1 chip token and a byte store costs 4. These did not help: `-Os` (+2.1%), `-Oz` (+11.5%), `-mno-relax` (+7.5%), plain `-O3` (-0.5%), function reordering (no change). Visual tradeoffs outside the default build: the `lite` preset cuts another 12.2% and `fast` cuts 40.2%, at the same 15 fps.
</details>

## 🗺️ The journey

<p align="center"><img src="docs/assets/journey.svg" alt="Journey timeline from the v0.11 viewer to the clip" width="100%"></p>

What worked ✅ (all in [`docs/research/experiments/`](docs/research/experiments/)):

- A real-WAD BSP viewer on Freedoom, then a DOOM engine port (DMC100) squeezed into 32 KiB.
- A takeover mode where `/bin/doomd` gets all the RAM, and a compact kernel core.
- Instruction diet: perf, syscall squeeze, renderer work, and frame skip (mean cost per tic cut from 10.47 M to 3.52 M instr in the first rounds).
- A live shell with a key ring, so you can type your way into DOOM.
- Chunk ROM: disk reads served from the data ROM (165,054 down to 4 requests).
- Real model runs on an A100: probe, title frame, cold boot.

What did not ❌ (see [dead ends](docs/research/experiments/99-dead-ends-and-open-gaps.md)):

- Vanilla doomgeneric: needs hundreds of KB of RAM.
- 1 MiB RAM inside the model, and execute-from-RAM overlays: not possible on this CPU.
- Prefetching, random cache replacement, bigger caches, 80-column "max" preset, serial pixel dump on the model (78 k tokens per frame).

Start with the [research README](docs/research/README.md), then the [timeline](docs/research/TIMELINE.md) and [reproduce](docs/research/REPRODUCE.md). Older per-version notes live in [docs/HISTORY.md](docs/HISTORY.md).
