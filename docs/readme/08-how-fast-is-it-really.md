Short answer: **very slow, and we are upfront about it.** it needed about 18 minutes per frame before; the current stack projects to about 8 to 10. 😅 Here it is in human units. All of these are *derived from the clip ledger* ([`docs/CLIP_LEDGER.md`](docs/CLIP_LEDGER.md)), not separately measured.

| Question | Plain English | Derivation |
|---|---|---|
| ⏱️ One displayed frame, before (patched driver) | about **18 minutes** of GPU time | 1.80 M instr per frame / 1,679 instr/s = about 1,072 s |
| 🚀 One displayed frame, now (**projection**) | about **8 to 10 minutes** | 1.61 M (tuned build) to 1.80 M instr per frame at 3,121 to 3,562 instr/s = about 450 to 580 s. Arithmetic on measured chunk speeds, not a full-clip run |
| 🎲 One game tic | about **5 minutes** of GPU time | 485,801 mean instr per tic (tics 30-300) / 1,679 instr/s = about 290 s |
| 🎞️ The whole 3 s clip, one GPU | about **13 hours** of serial GPU time | 81,065,587 instr / 1,679 instr/s = about 48,300 s (we ran it in parallel across 35 chunks) |
| 🏁 Needed for real time at 15 fps | **0.067 s** per frame | 1 / 15 |
| 📉 The gap | about **16,000x** too slow | 1,072 s / 0.067 s |

<p align="center"><img src="docs/assets/speed-ladder.svg" alt="Log-scale bars: about 45 minutes per frame at the original speed, about 18 minutes with the patched driver, a projected 8 to 10 minutes now, 0.067 seconds for real time" width="100%"></p>

**The derivation, step by step** 🧮

> 📝 **Footnote:** you may see about 28 min per frame if you divide the whole 3 s clip's chunk wall time (76,399 s over 45 frames, see [`docs/CLIP_LEDGER.md`](docs/CLIP_LEDGER.md)) by 45. That number is not representative: it includes the slow early chunks that ran on the original, unpatched driver (672 instr/s, GPU about 15% busy), cold-boot cost, and mixed GPU types. 18 min is the steady-state speed of the patched driver at the 1,679 instr/s median.

1. The clip has 45 frames and the run plan is **81,065,587** guest instructions. 81,065,587 / 45 = **1.80 M instructions per frame**.
2. The model's measured speed (A100) is the median over the 35 chunks: **1,679 instr/s** on the patched driver. The original run was **672 instr/s**.
3. 1.80 M / 1,679 = about 1,072 s, which is about **18 minutes**. At 672 instr/s the same frame would take about 45 minutes.
4. Real time at 15 fps needs a frame every 0.067 s. 1,072 / 0.067 is about **16,000**.

<p align="center"><img src="docs/assets/where-time-goes.svg" alt="Animated pipeline: guest instruction, chip tokens, GPU step, host loop, verify" width="100%"></p>

### 🧪 Speed-up experiments (tonight's work)

> ⚠️ **Host emulator numbers, not Qwen.** These count guest instructions and chip tokens on the host emulator (`rv32_fast`). They say how much less work the model would have to do; none of them has been run on the Qwen model yet (only Zba and the first chunks were confirmed on the real model). Compiler, hotloops, sim, bbtrace, combined, ktoken, presets, the B200 doc and the neural-executor research are **now merged to main**.

> ⚠️ **Which build made the 3 s clip?** The published 3 s clip was produced and model-verified with the **OLD build** (`TUNED=0` reproduces that build). The new default build (LTO + Zba + hot-loop + sim changes) is regress-verified on the host emulator, and Zba and the first chunks are confirmed on the real model, but the **full 3 s clip has NOT been re-verified on the model with the new build** (unless this note is later updated).

| Experiment | Result (host emulator) | Branch | Status |
|---|---|---|---|
| 🛠️ Compiler: LTO + Zba, hot code `-O3`, cold code `-Os` | **-8.88 %** instructions, **-8.0 %** chip tokens | `perf/compiler` | merged to main |
| 🔁 Hot loop: fill magnified wall columns by texel runs | **-7.60 %** instructions, **-11.33 %** chip tokens (on top of the compiler row) | `perf/hotloops` | merged to main |
| ➕ Cumulative (both rows) | **-15.8 %** instructions, **-18.4 %** chip tokens vs the original | `perf/hotloops` | merged to main |
| 🧹 Sim: `memcpy`/`memset` and `FixedDiv` fast paths (exact, same output) | **-1.12 %** instructions, **-1.03 %** chip tokens | `perf/sim` | merged to main |
| 🧮 Combined (all of the above), 350-tic dry run | **150,159,521** instructions (**-16.83 %**) and **208,776,718** chip tokens (**-19.40 %**) vs the original; 3 s clip **72,277,308** vs **81,065,587** instructions (**-10.8 %**). Host emulator, see [`docs/research/COMBINED.md`](docs/research/COMBINED.md) | `perf/combined` | merged to main |
| 🎚️ Visual presets `fast` / `lite` | **-40 %** / **-12 %** (at 15 fps) | `perf/presets` | merged to main. A **visual tradeoff**, the picture looks worse |
| 🔬 Basic-block trace: where the work is | hottest block `R_ColumnLoop` is 18.1 % of instructions; the top 100 blocks cover 65.7 %. Fusing blocks into the weights would save only **2-5 %** of tokens and needs a circuit rebuild, so we are not doing it | `perf/bbtrace` | merged to main |
| ⚙️ Fused/split Triton executor kernels + block verification (**real model**, A100, chunk c34, lockstep 0 errors, bit-exact kernels) | **2.02x**: K=64 + `--fast-kernels` **4,510** chip tok/s, **3,121** instr/s, **349.4 s** vs baseline **2,233** tok/s, **1,546** instr/s, **705.6 s**. See [`docs/research/PERF_LEDGER.md`](docs/research/PERF_LEDGER.md) | `perf/ktoken` | merged to main |
| 🧠 Neural-executor speed-up analysis (research and host-only prototypes) | analysis only, nothing run on the model; see [`docs/research/`](docs/research/) | `perf/neural-exec` | merged to main |
| 🅱️ B200 microbenchmark attempt | see [`docs/research/B200.md`](docs/research/B200.md) | `perf/b200` | merged to main |
| 🧾 Old vs combined **model** benchmark (**real model**, Modal A100-40GB, lockstep on, 0 errors, first chunk from reset, final build `1a718be0`) | OLD K=0: 1,819,896 instr / 2,564,928 chip tokens in **1,088.5 s** = 1,672 instr/s, 2,356 tok/s (598.1 s per M instr, 424.4 s per M tok). OLD K=64: 745.6 s, 2,441 instr/s, 3,440 tok/s (409.7 / 290.7). **COMBINED** K=64 + `--fast-kernels`: 3,111,015 instr / 4,410,315 tokens in **873.4 s** = 3,562 instr/s, 5,050 tok/s (280.7 s per M instr, 198.0 s per M tok) = **2.14x per chip token** vs OLD K=0. The chunks cover different boot work, so compare per million; the combined row mixes build, driver and kernel gains; COMBINED at K=0 was not run. Projection (arithmetic): the full clip serial on one A100 is about **20,300 s** at the combined rate vs about 48,500 s at the old K=0 rate. See [`docs/research/PERF_LEDGER.md`](docs/research/PERF_LEDGER.md) | `perf/ktoken` | measured, ledger merged here |

### 🖥️ Measured on the real model (Modal)

> These rows were **measured on the real model, on Modal GPUs**, not on the host emulator.

**E1: how fast can one token go?** Microseconds per chip token (lower is better), on the real model. Columns: graph only / with the host loop / K=16 tokens per graph.

| GPU | graph only | host loop | K=16 per graph |
|---|---|---|---|
| A100 | 242 | 283 | 242 |
| A10G | 319 | 372 | 319 |
| L4 | 193 | 239 | 193 |
| L40S | 165 | 186 | 167 |
| H100 | 203 | 225 | 205 |
| B200 | could not be scheduled on Modal, $0 spent, unavailable | | |

The GPU kernels (36 per token: attention head 50 %, FFN 32 %, apply 15 %) are the floor. Faster GPUs barely help: an H100 is only 1.19x an A100. The host loop adds about 15 % on top, and K=16 per graph removes it. Branch status: measurement only, no code change to merge.

**E3: verify K tokens in bulk (A100, one chunk, c34, 1.58 M chip tokens).** Every token is still compared to the oracle, with zero lockstep errors.

| K | instr/s | chunk time | speed-up |
|---|---|---|---|
| 0 (baseline) | 1,546 | 705.6 s | 1.00x |
| 16 | 2,275 | 479 s | 1.47x |
| 64 | 2,353 | 464 s | 1.52x |
| 256 | 2,375 | 459 s | 1.54x |

Branch `perf/ktoken`, now merged to main.

**E4: fixed costs.** A text token costs 45 ms warm, plus 0.21 s fixed per segment.

**Why not seconds?** 18 minutes was the earlier speed and the stack now projects to 8-10 minutes, but each token costs about 240 us of GPU kernel time on an A100 (the floor today), and a frame needs about 1.8 M instructions, roughly 2.5 M tokens. Three levers remain: fewer instructions (compiler, hot loops, presets), less overhead per token (block verification, 1.54x measured), and faster kernels (split/fused kernels measured 2.02x together with block verification, see the table above). The final old-vs-combined benchmark is the pending row above.

<p align="center"><img src="docs/assets/bottleneck-pie.svg" alt="Pie chart of instruction share by function: R_ColumnLoop 18.7 percent, R_ReplayWall 12.2, rec_get 7.7, rc_fill 4.5, everything else 56.9" width="100%"></p>
