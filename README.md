<div align="center">

<img src="assets/hero.svg" alt="QwenOS" width="100%">

# 🎮 QwenOS

**A tiny operating system that boots, opens a shell and runs real DOOM on Qwenputer: a 32-bit RISC-V CPU compiled into the weights of Qwen3.5-4B**

![CPU: RV32IM](https://img.shields.io/badge/CPU-RV32IM-5b8def) ![RAM: 32 KiB](https://img.shields.io/badge/RAM-32%20KiB-f2c14e) ![engine: DMC100-Doom](https://img.shields.io/badge/engine-DMC100--Doom-c0392b) ![model: Qwen3.5-4B](https://img.shields.io/badge/model-Qwen3.5--4B-7e57c2) ![clip frames model-verified: 45 of 45](https://img.shields.io/badge/clip%20frames%20model--verified-45%20of%2045-3ddc97) ![model chunks: 35](https://img.shields.io/badge/model%20chunks-35-27c8e8) [![license: MIT + GPL-2.0](https://img.shields.io/badge/license-MIT%20%2B%20GPL--2.0-lightgrey)](LICENSE) ![status: research demo](https://img.shields.io/badge/status-research%20demo-lightgrey) [![release: v0.1.0](https://img.shields.io/badge/release-v0.1.0-27c8e8?logo=github&logoColor=white)](https://github.com/Bobliuuu/qwen-os/releases/tag/v0.1.0) [![Hugging Face: run ledgers](https://img.shields.io/badge/Hugging%20Face-run%20ledgers-ffd21e?logo=huggingface&logoColor=white)](https://huggingface.co/datasets/Bobliu/qwen-os)

[🎬 Video](#video) · [📊 At a glance](#results) · [⚡ Quick start](#what-you-can-do-in-30-seconds) · [🧩 How it works](#how-it-works-in-one-picture) · [🐢 How fast](#how-fast-is-it-really) · [🔍 What is real](#what-is-real-and-what-is-not) · [🎞️ The clip](#the-3-second-clip) · [🙋 FAQ](#faq-for-humans) · [🗺️ Repo map](#repo-map)

</div>

---

**Explainer video (voice-over and subtitles): what QwenOS is, what the Qwen model actually verified, and what is not real**

[![Explainer video preview (click for the mp4)](video/preview.gif)](video/qwenos_explainer.mp4)

> ### 🧾 TL;DR
> - 🧠 **What:** a 32-bit RISC-V CPU ([Qwenputer](https://github.com/divagr18/qwenputer)) is built into the layers of Qwen3.5. We wrote a small OS for it and ran the real DOOM engine on top.
> - 🎨 **The model emits the pixels itself:** the model **emits the pixels itself**. The guest dumps each frame as about 32,100 console bytes, every byte comes out of the model as a BYTE token, and every token is checked against a lockstep oracle. The typed flow (`help`, `ls`, `run /bin/doomd`, then frame markers 1-3) is also model-verified ([details](docs/research/TYPED_FLOW_MODEL.md)).
> - 🎯 **Progress:** see the progress line just below. We only count a frame once its model-emitted pixels match the emulator byte for byte.
> - 🐌 **Catch:** slow. One displayed frame took about **18 minutes** of GPU time before (patched driver). With the speed-ups we project about **8 to 10 minutes** per frame (arithmetic, not a measurement). Real time is 0.067 s per frame, so we are still thousands of times too slow.
> - 🔍 **Honest bit:** keys are scripted (or come through the key ring), the clock is virtual, the host serves the disk and collects the bytes into PNGs. Details below.
> - 🕹️ **Play it:** `make live-doom` on the host emulator (not the model). See [boot it yourself](#-watch-it-boot-then-play-it).

<!-- V2:PROGRESS -->
🎯 **All 45 frames were verified through the model. After the optimizations, the clip was retested with the model emitting the pixels too** (byte-exact vs the emulator, zero lockstep divergence; the retest covers 12 of the 45 frames).
<!-- /V2:PROGRESS -->

<a id="results"></a>

## 📊 At a glance

Measured results of the 3-second E1M1 clip and the typed flow, read from the provenance ledger ([`docs/CLIP_LEDGER.md`](docs/CLIP_LEDGER.md)) and `docs/research/typed-flow/`.

| Clip frames model-verified | Model chunks | Guest instructions | Chip tokens |
|:---:|:---:|:---:|:---:|
| **45** | **35** | **81.07 M** | **116.3 M** |

**Where the 35 chunks of the clip ran**

| Lane | Chunks | Instructions | Model wall time (h) |
| :--- | ---: | ---: | ---: |
| Modal A100 | 29 | 67,673,668 | 18.74 |
| AWS A10G | 3 | 6,056,587 | 1.17 |
| Lambda A100 | 3 | 7,335,336 | 1.31 |

<sub>Source: `docs/derived/readme_data.json`</sub>

**Typed flow on the model (Modal A100): cold boot, help, ls, run /bin/doomd, frame markers 1 to 3**

| Step | Segments | Instructions | Chip tokens | instr/s | GPU |
| :--- | ---: | ---: | ---: | ---: | :--- |
| boot to prompt, help | 24 | 1,246,050 | 1,766,142 | 2,242 | A100-SXM4-40GB |
| ls | 1 | 1,031,152 | 1,460,263 | 2,398 | A100-SXM4-40GB |
| run /bin/doomd, first marker | 1 | 1,057,870 | 1,467,197 | 2,210 | A100-SXM4-80GB |
| frame markers 2 and 3 | 1 | 4,904,118 | 7,015,050 | 2,680 | A100-SXM4-40GB |

<sub>Source: `docs/derived/readme_data.json`</sub>

<p align="center"><img src="assets/frame_instr.svg" alt="Guest instructions per displayed frame (millions), 45-frame E1M1 clip" width="100%"></p>

<p align="center"><img src="assets/lane_hours.svg" alt="Model wall time by GPU lane, 35 chunks (hours)" width="100%"></p>

<p align="center"><img src="assets/typed_instr.svg" alt="Typed flow on the model: instructions per step (millions)" width="100%"></p>

<p align="center"><img src="assets/stack.svg" alt="QwenOS on a CPU inside Qwen3.5-4B, checked token by token" width="100%"></p>

<p align="center"><img src="video/preview.gif" alt="animated overview of the explainer video" width="70%"></p>

<details>
<summary>All 35 clip chunks</summary>

**All 35 clip chunks (from the provenance ledger)**

| Chunk | Instructions | Chip tokens | Lane | Wall s |
| :--- | ---: | ---: | :--- | ---: |
| c00 | 1,819,896 | 2,564,928 | Modal A100 | 2,471.1 |
| c01 | 1,597,830 | 2,232,547 | Modal A100 | 1,994.3 |
| c02 | 2,432,641 | 3,481,364 | Modal A100 | 5,493.0 |
| c03 | 2,458,771 | 3,518,372 | Modal A100 | 4,732.6 |
| c04 | 2,437,969 | 3,489,392 | Modal A100 | 2,351.7 |
| c05 | 2,501,405 | 3,584,517 | Modal A100 | 4,957.5 |
| c06 | 2,528,685 | 3,632,609 | Modal A100 | 2,552.2 |
| c07 | 2,596,858 | 3,724,842 | Modal A100 | 4,205.7 |
| c08 | 2,782,065 | 3,986,282 | Modal A100 | 6,034.9 |
| c09 | 2,686,905 | 3,826,544 | Modal A100 | 5,835.4 |
| c10 | 2,264,907 | 3,228,958 | Modal A100 | 2,088.7 |
| c11 | 2,335,547 | 3,334,059 | Modal A100 | 1,350.8 |
| c12 | 2,254,038 | 3,225,633 | Modal A100 | 1,249.6 |
| c13 | 2,148,527 | 3,080,501 | Modal A100 | 1,195.6 |
| c14 | 2,047,702 | 2,950,102 | Modal A100 | 1,143.9 |
| c15 | 2,078,255 | 2,990,224 | Modal A100 | 1,247.6 |
| c16 | 2,176,807 | 3,111,636 | Modal A100 | 1,299.2 |
| c17 | 2,294,193 | 3,260,708 | Modal A100 | 1,392.6 |
| c18 | 2,117,038 | 3,035,715 | Modal A100 | 1,443.0 |
| c19 | 2,036,052 | 2,947,021 | Modal A100 | 1,246.1 |
| c20 | 2,094,260 | 3,018,532 | Modal A100 | 1,285.8 |
| c21 | 1,986,855 | 2,860,493 | Modal A100 | 1,231.4 |
| c22 | 1,864,166 | 2,688,213 | Modal A100 | 1,165.8 |
| c23 | 3,096,915 | 4,460,668 | Modal A100 | 1,984.7 |
| c24 | 2,601,842 | 3,770,019 | Modal A100 | 1,463.6 |
| c25 | 2,383,968 | 3,476,165 | Modal A100 | 1,394.9 |
| c26 | 2,549,440 | 3,702,596 | Modal A100 | 1,457.0 |
| c27 | 2,553,600 | 3,677,006 | Modal A100 | 1,469.9 |
| c28 | 2,946,531 | 4,205,280 | Modal A100 | 1,738.2 |
| c29 | 2,546,108 | 3,660,576 | AWS A10G | 1,755.7 |
| c30 | 2,565,887 | 3,686,177 | Lambda A100 | 1,641.3 |
| c31 | 2,314,444 | 3,344,358 | Lambda A100 | 1,495.5 |
| c32 | 2,455,005 | 3,524,411 | Lambda A100 | 1,576.0 |
| c33 | 2,419,771 | 3,476,641 | AWS A10G | 1,678.0 |
| c34 | 1,090,708 | 1,575,918 | AWS A10G | 775.0 |

<sub>Source: `docs/derived/readme_data.json`</sub>

</details>

<a id="watch-it-boot-then-play-it"></a>

## 🎥 Watch it boot, then play it

```sh
make live-doom                    # fetches engine + Freedoom on first run, boots QwenOS, shell prompt, then type `doom`
make live-doom LIVE_ARGS=--auto   # same, with a typed shell tour
```

<p align="center"><img src="docs/assets/qwenos-live-boot.gif" alt="Recorded live terminal: QwenOS boots, a shell prompt, then DOOM E1M1" width="640"><br><a href="docs/assets/qwenos-live-boot.mp4">MP4</a> · <a href="docs/LIVE_DEMO.md">docs/LIVE_DEMO.md</a></p>

**Honest label: this is tier T0, the host emulator** (`rv32_fast` on your CPU), not the Qwen model. The terminal banner says `tier T0`. On the model a frame took about 18 minutes before the speed-ups and projects to 8-10 with them (see the speed section); the recording is the emulator running the same guest code (kernel, shell, DOOM). Guide, tiers and the model path (T2): [`docs/LIVE_DEMO.md`](docs/LIVE_DEMO.md).

<a id="how-it-works-in-one-picture"></a>

## 🧩 How it works in one picture

<p align="center"><img src="docs/assets/stack.svg" alt="Animated stack: you, shell, doomd, DMC100 engine, kernel syscalls, Qwenputer circuit inside Qwen3.5" width="100%"></p>

Want the picture book? [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) has one animation per idea.

<a id="where-the-pixels-come-from"></a>

## 🖼️ Where the pixels come from

<p align="center"><img src="docs/assets/pixels-arch.svg" alt="Animated pipeline: DOOM engine, LCD dump routine, Qwen chip emitting BYTE tokens, lockstep oracle, host writing the PNG" width="100%"></p>

1. 👾 The **real DOOM engine** (guest RISC-V code in ROM) draws a frame into the guest framebuffer.
2. 📤 A **guest dump routine** (same ROM) writes the frame to the console: about **32,100 bytes** per frame, rows 0-199. The status-bar rows (208-239) are not in a frame's dump.
3. 🧠 The **Qwen3.5-4B chip** executes every one of those instructions inside its weights, and each pixel byte comes out as a **BYTE token**.
4. ✅ The **lockstep oracle** compares every token with a reference CPU. One wrong token would be a divergence. We count zero.
5. 🖥️ The **host** only collects the bytes, applies the palette and writes the PNG.

**What is a BYTE token?** The model normally generates "chip tokens" that carry out an instruction. When the guest writes a byte to the console, the model emits that byte itself as a special BYTE token. So a pixel is literally generated text.

**Why were the first clip's pixels read by the emulator?** Dumping a frame is extra work for the model (about 32,100 more bytes per frame), so for the first 3 s clip we had the emulator read the frame out of guest memory and spent the model's time verifying the instruction trace. The research notes list an early serial pixel dump (78 k tokens per frame) among the dead ends for the same reason. After the optimizations below, we retested the clip with the model paying that cost too: it emits every pixel byte itself.

**Retest on the optimized build, model-decoded pixels (MP4 plays at 15 fps, the GIF is slowed to 4 fps):** [MP4](docs/assets/qwenos-doom-modelpixels.mp4)

<p align="center"><img src="docs/assets/qwenos-doom-modelpixels.gif" alt="DOOM frames from the retest, every pixel byte emitted by the Qwen model" width="480"></p>

---

<a id="three-ways-to-run-the-same-cpu-t0-t1-t2"></a>

## 🧬 Three ways to run the same CPU (T0, T1, T2)

<p align="center"><img src="docs/assets/tiers.svg" alt="Animated: one RISC-V program feeds three executors, T0 fast emulator, T1 reference oracle, T2 the Qwen model, and a compare step checks same state, same bytes" width="100%"></p>

The same RISC-V program can be run by three executors that are meant to be **bit-identical**: they should produce the same state and the same bytes.

- **T2** is the real Qwen3.5-4B model on a GPU. It is the point of the project, and it is slow (about 3-4 thousand instructions per second).
- **T1** is the upstream Qwenputer reference CPU (`chipformer.rv.ref.Machine`), the oracle. In a model run, every token the model predicts is compared with it, and slow blocks are re-decoded and checked too (`tools/model_doom_qwen.py`, `bridge.Session`). A mismatch stops the run.
- **T0** is our fast C emulator `tools/rv32_fast.c` (plus our Python reference `tools/rv32_qwenputer.py`). It is a fast twin of the same CPU, used to plan chunks, snapshot, benchmark and run the live demo.
- The oracle checks the **chip execution**. The host still handles keys, the disk, the roughly 30-token tool-call turn per segment, the 35 boundary instructions and the snapshots.
- What we saw: the model run was compared token by token with the oracle with **zero divergence** for the 45-frame clip (35 chunks), the typed flow (27 segments) and the first model-decoded pixel frames. T0 equals T1 on everything we tested: per-tic state hashes and frame hashes against goldens (`tools/doomd_regress.sh`, `tests/golden`), a 3-way lockstep (`tests/test_upstream_doomd.py`), and `rv32_fast`'s token-cost model, which matched `ref.Machine` exactly on 3,000,000 instructions. This is observed equality, not a mathematical proof.

| Tier | What runs it | Speed | Used for | What it shows |
|---|---|---|---|---|
| T0 | `rv32_fast` (C) and our Python reference | tens of millions of instr/s (180 M instructions traced in about 4 s) | planning, snapshots, benchmarks, the live demo | same hashes as the goldens and as T1 on the tested runs |
| T1 | upstream `ref.Machine` | about 140 k instr/s (measured in the model-driver runs) | oracle for every model token | the model's tokens match it, with no divergence on the runs listed |
| T2 | the Qwen3.5-4B model on a GPU | about 3-4 thousand instr/s (A100) | the clip, the typed flow, the pixels | the circuit in the weights runs the program |

**Caveats we know about.** The 3-way lockstep was run on the original build. The tuned build adds Zba (`sh1add/sh2add/sh3add`) to `rv32_fast.c`, and our Python reference `tools/rv32_qwenputer.py` has no Zba, so it cannot replay that build. The upstream oracle did accept the Zba instructions on the real-model runs with zero divergence, but the 3-way upstream lockstep test was not rerun for the newest tuned build ([`COMPILER_BENCH.md`](docs/research/COMPILER_BENCH.md)). More in [`HONESTY.md`](docs/research/HONESTY.md).

**Which tier is which claim?** The live demo video is **T0 only**. The 3-second clip, the typed flow and the model-decoded pixels are **T2 with T1 as the oracle**. The speed numbers in [how fast is it](#-how-fast-is-it-really) are T0 instruction counts unless they say "real model".

<a id="how-a-keypress-reaches-the-os"></a>

## ⌨️ How a keypress reaches the OS

<p align="center"><img src="docs/assets/keyring.gif" alt="Animated: the host writes the ASCII byte 0x68 into the mailbox at 0x154 while the guest is parked; the kernel compares the mailbox counter with its read count and returns the key to the shell" width="100%"><br><sub>Animated SVG version: <a href="docs/assets/keyring.svg">docs/assets/keyring.svg</a></sub></p>

The CPU has no keyboard hardware, no interrupts and no privilege levels, so the OS cannot be told that a key arrived. It has to ask, and the host has to hand the key over at a safe moment. That is the key ring:

- 📮 **The mailbox.** 8 bytes of RAM at the hardcoded address `0x154` (it lives in the model's state): a `u32 seq` counting the keys the host has pushed, and a ring of four byte slots `q[4]`. Key number `n` lives in `q[n & 3]`. A key is a plain ASCII byte (`h` is `0x68`); 0 means "no key".
- 🖥️ **The host pushes.** It writes the byte into `q[seq & 3]` first and adds 1 to `seq` last, so the guest never sees a count without its byte. The host only does this while the guest is parked (below).
- 🧠 **The kernel notices by comparing two counters.** The shell calls the `KEY_WAIT` syscall (number 22). The kernel keeps its own read count at `0x140` and compares it with `seq`: if they match there is no new key; if `seq` is ahead it returns `q[count & 3]` and bumps its read count. If the host gets more than 4 keys ahead, the oldest are dropped.
- ⏸️ **Parking.** When there is no key, `key_wait` loops through `qos_key_park`, a single `ret` in kernel ROM at pc `0x40044`. It does nothing, but it is a known address where the guest is idle. In the model run, the driver put a ROM breakpoint there: the segment stops before the `ret`, the host pushes one character, runs that `ret`, and the next segment starts from that state. Every key is therefore present at the same instruction where the emulator consumed it, and the guest itself chooses where the pause is.
- 🔤 **Typed in the model run:** `help`, `ls`, `run /bin/doomd`, each followed by Enter: 23 keys. The park `ret`s are among the host-executed boundary instructions counted in [what is real](#-what-is-real-and-what-is-not).
- 🎮 **After `run /bin/doomd`,** DOOM reads the same ring once per game tic and maps each byte to its own input. The engine was built for a handheld with physical buttons, so `w`, `s`, `a`, `d`, space or `f`, `e` and Esc or `m` become presses of its forward, back, turn, fire, use and menu buttons. A keyboard byte arrives once but a button must be held, so each key counts as a press held for 120 ms of virtual time (about 4 tics). The terminal viewer turns the arrow keys into `w`, `s`, `a`, `d`.
- 🎞️ **The 3-second clip skipped all of this.** Its input was a compiled-in script (`q_script`), not the key ring.

In a real OS the same job is done by a keyboard interrupt, a driver that translates scancodes, a kernel ring buffer, a TTY layer, and a scheduler that wakes the sleeping program. Here the host stands in for the keyboard hardware, polling and parking stand in for interrupts and sleeping, and there is no scancode layer.

<a id="what-is-this"></a>

## 💡 What is this?

Imagine a computer made of attention layers. That is [Qwenputer](https://github.com/divagr18/qwenputer): a 32-bit RISC-V CPU (RV32IM) compiled into the layers of Qwen3.5, where every instruction is a few generated tokens.
QwenOS is the little OS we gave it: a kernel, a shell, a keyboard, a 32x24 framebuffer and a block disk, all squeezed into **32 KiB of RAM** 🤏.
Then we asked it to run a *real* DOOM engine ([DMC100-Doom](https://github.com/ArturBieniek4/DMC100-Doom) on [Freedoom](https://freedoom.github.io) data) as an ordinary program, `/bin/doomd`.
Architecture is inspired by [bobliu-os](https://github.com/Bobliuuu/bobliu-os).

> **Honest summary:** the whole thing works on an emulator, and the real Qwen model has verified, in lockstep: a cold boot to the first frame marker, the typed flow (`help`, `ls`, `run /bin/doomd`, first DOOM frame marker plus two more: 4 Modal A100 chunks, 8,239,190 instructions, 27 segments, zero divergence, 273 console bytes through marker 1 identical to the emulator; [details](docs/research/TYPED_FLOW_MODEL.md)), and all 45 frames of the first 3 s clip (35 chunks) as an instruction trace. In that clip the emulator read the pixels out of memory; now the model emits them; the number of frames done so far is in the progress line above. We do not claim 45 of 45 model-decoded frames until it is true.

<a id="what-you-can-do-in-30-seconds"></a>

## ⚡ What you can do in 30 seconds

You need Clang/LLD, `readelf` and Python 3. No game data is in this repo.

```sh
make check                    # kernel, layout, Python reference CPU, unit tests (no WAD needed)
make demo-elf                 # scripted E1M1 image -> build/demo/qwenos-e1m1.elf (+ chunk-ROM plan)
make live-doom                # THE command: fetches engine+Freedoom on first run, boots QwenOS (T0 emulator), shell, then type `doom`
make live-doom LIVE_ARGS=--auto   # same, but it types a shell tour and `run /bin/doomd` for you
# step by step + real-model (T2, GPU) path: docs/LIVE_DEMO.md
```

`demo-elf` and the live terminal need the engine and a WAD, see [get the engine](#-get-the-engine-and-freedoom). In the live terminal, arrow keys (or w/s/a/d) move, f or space fires, e uses, and `Ctrl-]` quits.
Other handy targets: `CHUNKROM=1 make demo-live` (typed-flow image) and `tools/doomd_regress.sh` (frame and state goldens).

<a id="how-fast-is-it-really"></a>

## 🐢 How fast is it, really?

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

<a id="the-numbers"></a>

## 📊 The numbers

All from [`docs/research/STATUS.md`](docs/research/STATUS.md), [`MERGE_NOTES.md`](MERGE_NOTES.md) and the [provenance ledger](docs/research/TRACES/PROVENANCE.md). Instruction counts are guest RV32 instructions. "Plain English" is our conversion, using the median 1,679 instr/s where a time is given.

| Thing | Value | Plain English |
|---|---|---|
| 🧠 RAM | 32 KiB (doomd owns 30,800 B while it runs) | 0.03 MiB |
| 📀 Exec ROM / data ROM | 256 KiB / 128 KiB, both read-only | |
| 🔤 Chip tokens per instruction | 1.345 (measured on the model boot) | |
| ⌨️ Typed flow: boot to prompt | 186 instr | about a tenth of a second at 1,679 instr/s |
| 🥾 Cold boot to first E1M1 frame | 2.9 M to 3.7 M instr, depending on build | roughly 30 to 40 minutes at 1,679 instr/s |
| 🎲 Mean instr per game tic, tics 30-300 (FULL preset) | 485,801 with host-served disk, 538,573 with chunk ROM | about 5 minutes per tic |
| 🕐 350 tics of E1M1, total | 180.5 M instr (165,054 disk requests) or 199.7 M with chunk ROM | about 30 hours on one GPU |
| 💽 Disk requests with chunk ROM | **4** in total, 0 inside doomd (down from 165,054) | |
| 📦 Chunk-ROM price | +10.6 % instructions | |
| 🚀 Model speed, A100-SXM4-40GB, end to end (boot run) | 1,454 chip tokens/s, about 1.1 k instr/s | |
| 📚 doomd stack headroom | 960 B used of 1,408 B reserved | |

FULL preset means a 160x200 low-detail view, game logic every tic, and 15 of every 35 tics drawn. Instructions per tic are means over all tics, skipped draws included.

<a id="what-is-real-and-what-is-not"></a>

## 🔍 What is real and what is not

<p align="center"><img src="docs/assets/verified-vs-host.svg" alt="Two columns: what the Qwen model checked in lockstep, and what the host did" width="100%"></p>

| Tier | Who ran it | What it has verified |
|---|---|---|
| 🟦 T0 | C emulator `tools/rv32_fast` and our Python reference | Everything: typed flow, E1M1 gameplay, chunk ROM, regression goldens, a 1060-frame scripted E1M1 video |
| 🟨 T1 | Upstream reference CPU (`chipformer.rv.ref.Machine`), the oracle (see [three ways to run the CPU](#-three-ways-to-run-the-same-cpu-t0-t1-t2)) | Lockstep equal to the emulator for 6,000,000 instr of the merged build (level load and 2 frames); upstream also boots the kernel (120,267 instr) |
| 🟩 T2 | The real Qwen model (merged Qwen3.5-4B, A100) with a lockstep oracle | Probe; title frame (6,563 instr); **cold boot to the first frame marker: 1,552,382 instr, 292 segments, zero divergence**, on an earlier (pre-merge) build |
| 🟩 T2, gameplay | The real Qwen model (Qwen3.5-4B, lockstep oracle) | The 3-second E1M1 clip: 45 frames, 35 chunks, 81,065,587 instr, zero divergence, scripted input (see [the clip](#-the-3-second-clip)). The typed `run /bin/doomd` flow is a separate run, see the next row |
| 🟩 T2, typed flow | The real Qwen model, lockstep oracle | Cold boot, `help`, `ls`, `run /bin/doomd`, first DOOM frame marker and markers 2 and 3: 8,239,190 instr in total, about 11.7 M chip tokens, 27 segments, 4 A100 chunks, zero divergence, every token checked against the oracle. Console through marker 1: 273 bytes byte-identical to the C emulator and the Python reference; through marker 3 the first 315 bytes are identical (the model segment stops at the first not-yet-executed pc after the marker, so it prints 20 extra bytes `DOOMD_FRAME 3 tic 5` and runs about 15k instructions past the emulator's marker). See [TYPED_FLOW_MODEL](docs/research/TYPED_FLOW_MODEL.md) |
| 🟩 T2, pixels | The real Qwen model, lockstep oracle | The guest's LCD dump stream (about 32,100 console bytes per frame, rows 0-199) comes out as model BYTE tokens, each lockstep-checked; the host collects the bytes into PNGs. **retested on the optimized build, byte-exact on rows 0-199; see the progress line at the top** |

Things you should know before you get too excited 🧯:

- 💽 **Disk** is host-served block storage, patched in between model segments. With chunk ROM it is mostly read from the data ROM instead. It is not stored in the weights.
- ⌨️ **Keyboard** input is simulated: the host pushes hardcoded keys through the input mailbox.
- 🕰️ **Clock** is virtual (about 1 ms per idle call), not real time.
- 🖼️ **Pixels**: all frames are genuine DOOM output. In the first clip the pixel bytes were read from guest memory by the emulator and the model verified the instruction trace. Now the model emits the pixel bytes (rows 0-199 only) and the host just collects them. A frame counts as model-decoded only when its bytes match the emulator.
- ⌨️ **Typed-flow run, disclosures** ([details](docs/research/TYPED_FLOW_MODEL.md)):
  - 22 boundary instructions (the park `ret`s) were executed by the host.
  - Keys were delivered at `qos_key_park` through the key ring, one char per park, so each key is present at the same instruction the emulator consumed it.
  - Only `help`, `ls` and `run /bin/doomd` were typed (no cat/echo tour), and no gameplay keys were sent during the frames.
  - The run used the older non-Zba chunk-ROM live ELF (built 2026-11-03), whose shell prints `?` for `help`.
  - The frames' pixels were not checked in that run (marker bytes only); model-decoded pixel frames are a separate run.
- 🧩 **Segments**: a model run is a series of host-snapshotted segments, and "zero divergence" is per segment.
- 🐌 **Not real-time.** See [how fast is it](#-how-fast-is-it-really).
- The clip uses a dedicated E1M1 demo build with scripted input; the typed flow was verified separately. Scope is E1M1.
- Full Python-reference replay covers only segments 1-4; the C twin covers segments 5-38. One chunk (c02) has an unexplained +5 instruction difference that we have not decoded.

Full list: [`docs/research/HONESTY.md`](docs/research/HONESTY.md).

<a id="the-3-second-clip"></a>

## 🎬 The 3-second clip

<p align="center"><img src="docs/assets/qwenos-doom-3s.gif" alt="The 3-second E1M1 clip, 45 frames at 15 fps" width="480"><br><a href="docs/assets/qwenos-doom-3s.mp4">Full-quality MP4 (960x720, 15 fps)</a> · <a href="docs/assets/qwenos-doom-3s-contact.png">contact sheet</a> · <a href="docs/CLIP_LEDGER.md">per-frame and per-chunk ledger</a></p>

> 📝 **Note on this clip:** it was generated with an **older build**. Since then the build got faster: the host emulator runs **-10.8 %** instructions on this clip, and on the real model we measured **2x** from block verification plus fused kernels (chunk c34, see the speed-up table). The optimized build was retested on the model with model-decoded pixels (see above).

E1M1, FULL preset (160x200 low-detail view, status bar), 15 rendered frames per 35 game tics. The player walks forward, turns right, fires the pistol and keeps walking. The input is a compiled-in script (`q_script`), not typed live.

| Field | Value |
|---|---|
| 🎞️ Frames in the clip | 45 (3 s at 15 fps), E1M1 |
| 🧱 Separate model runs stitched | 35 chunks: 29 Modal A100, 3 Lambda A100, 3 AWS A10G |
| ✅ Frames with a model-verified instruction trace | 45 of 45 (real Qwen3.5-based model, lockstep oracle, zero divergence) |
| 🔢 Instructions | 81,065,587 in the run plan; 81,065,591 executed by the model plus 35 host-executed boundary instructions |
| 💽 Disk requests | 4 in total (host-served disk replaced by chunk ROM) |

What "verified" means here: the model executed the instruction trace in lockstep with the oracle, and the frame markers and console bytes matched. **The frames are real output of the real DOOM engine**; the pixel bytes are read from the guest's memory by the emulator (same ELF and state), so Qwen verified the computation that made them, not the pixel values themselves. Disclosures: keys are simulated, the clock is virtual, the disk is host-served through chunk-ROM windows, 35 boundary instructions are host-executed, and each chunk starts from a host-supplied snapshot. Not covered by the clip: the typed flow (a separate run, see above); a full Python-reference replay (only segments 1-4, the C twin covers 5-38); and a +5 instruction difference in chunk c02 that we have not decoded. The original run plan failed instruction-count bookkeeping at the c00-c02 split boundary and was reconciled; the ledger links both.

<a id="faq-for-humans"></a>

## 🙋 FAQ for humans

<details>
<summary><b>🤔 What is this, in one sentence?</b></summary>

A real DOOM engine running on a tiny OS, on [Qwenputer](https://github.com/divagr18/qwenputer): an RV32IM CPU compiled (not trained) into the weights of Qwen3.5-4B. Every guest instruction is executed by the model's layers, one token at a time, and the 32 KiB of RAM lives in its Gated DeltaNet state (no KV cache). A computer made of transformer layers, playing DOOM, very slowly.
</details>

<details>
<summary><b>🐌 Why is it so slow?</b></summary>

Every guest instruction costs about 1.345 generated tokens, and the model produces tokens one after another. One DOOM frame is about 1.8 million instructions, so the GPU does millions of tiny sequential steps per frame. At the median 1,679 instr/s that is about 18 minutes. A normal CPU does the same work in a fraction of a millisecond.

Where do the instructions go? Mostly into drawing. Tics that draw a frame cost 1.1 to 2.2 M instructions, while a tic with no draw costs only about 16 to 37 k, so the median over all tics (about 138 k) looks small. Over the whole run, game logic is about 6 % and rendering about 94 %.
</details>

<details>
<summary><b>🧠 Is it really Qwen?</b></summary>

Yes. The model (merged Qwen3.5-4B carrying the Qwenputer circuit) executed 81,065,591 instructions of the clip with a lockstep oracle and zero divergence. The host executed 35 boundary instructions, serves disk, injects scripted keys, and starts each chunk from a snapshot. In the first clip Qwen did not emit the pixels (the emulator read them out of memory); now it does, one BYTE token at a time, and the progress line says how many frames are done. See [what is real](#-what-is-real-and-what-is-not).
</details>

<details>
<summary><b>🕹️ Can I play it?</b></summary>

Yes, on the host emulator (T0): `make live-doom` or `tools/qwenos_live.sh` gives an interactive terminal with arrows to move. Playing it on the model is not practical: one tic takes about 5 minutes. `make live-doom` is the one-command version (see [boot it yourself](#-watch-it-boot-then-play-it)).
</details>

<details>
<summary><b>🏎️ Why not just make it faster?</b></summary>

We are trying; see the [speed-up experiments](#-speed-up-experiments-tonights-work). The compiler and hot-loop work cut about 16 % of instructions on the host emulator. Even a 40 % cut would still leave a gap of thousands of times. The model speed (tokens per second) is the real wall, and instruction fusion inside the weights would save only 2-5 % of tokens.
</details>

<details>
<summary><b>🔤 What is a BYTE token, and why were the first clip's pixels read by the emulator?</b></summary>

A BYTE token is the model emitting one console byte as text. The first clip skipped the pixel dump to save model time and let the emulator read the frame; now the model pays that cost. See [where the pixels come from](#-where-the-pixels-come-from).
</details>

<details>
<summary><b>🖼️ Are the frames real?</b></summary>

Yes. They are the genuine output of the real DOOM engine running as guest code, not mockups. See the caption at the top and the [clip ledger](docs/CLIP_LEDGER.md) for every frame and chunk.
</details>

<a id="glossary"></a>

## 📖 Glossary

| Term | Meaning |
|---|---|
| 🎲 **tic** | One step of DOOM's game logic. DOOM runs 35 tics per second. |
| 🖼️ **frame** | One picture we actually draw. The clip draws 15 frames for every 35 tics (about 15 fps). |
| 🧱 **chunk** | One separate model run covering a slice of the trace. The clip is 35 chunks stitched together, each started from a host snapshot. |
| 🔒 **lockstep** | The model executes each instruction while an oracle (a trusted reference) executes the same one. Any mismatch is a divergence. We saw zero. |
| 🔤 **chip token** | A token the model generates as part of executing one guest instruction. About 1.345 per instruction. |
| 🟦🟨🟩 **T0 / T1 / T2** | Who ran the code. T0: the C emulator and our Python reference. T1: the upstream reference CPU, the oracle, checked against T0. T2: the real Qwen model with a lockstep oracle. |
| 🔤 **BYTE token** | The model emitting one console byte as text. Every pixel byte of a frame comes out this way. |
| 🧩 **segment** | A stretch of a model run between host interventions such as disk service. |
| 📀 **chunk ROM** | Game data served from a read-only ROM window, which cut disk requests from 165,054 to 4. |

<a id="get-the-engine-and-freedoom"></a>

## 📦 Get the engine and Freedoom

Neither is included.

```sh
make engine     # = tools/fetch_engine.sh: clone DMC100-Doom @0cdc78e into .deps/, apply the patch, fetch Freedoom 0.13.0, build E1.img
```

`ports/doomdmc/mkimage.sh` builds the NOR disk image (`E1.img`) from the layout and the WAD; `ports/doomdmc/build.sh` builds `doomd`. Override locations with `DMC`, `IWAD`, `QOS_FREEDOOM_WAD`.
The `engine-patches/` diff holds the QwenOS edits to DMC100-Doom (see `engine-patches/NOTICE`).

<a id="tests"></a>

## 🧪 Tests

`make check`; `tools/doomd_regress.sh` (state/frame goldens in `tests/golden/`); upstream lockstep needs a checkout of qwenputer on `PYTHONPATH` (see [`MERGE_NOTES.md`](MERGE_NOTES.md)).
`tools/model_doom_qwen.py` and `tools/model_doom_chunks.py` drive the real model and need a GPU box plus the Qwen checkpoint; they are not run in CI.

<a id="hardware-and-toolchain"></a>

## 🖥️ Hardware and toolchain

What this was built and run on.

| Role | Machine | Used for |
|---|---|---|
| Dev box | Apple M2 Pro (Mac14,12), 10 cores, 16 GB RAM, macOS 26.2 (arm64) | Kernel and engine builds, T0 emulator (`rv32_fast`: 180.5 M instr in about 4 s), T1 oracle runs, video and GIF rendering |
| Main GPU | NVIDIA A100-SXM4-40GB on Modal (about $2.10/h) | The real-model runs: the 45-frame clip chunks, the typed boot flow, the model-decoded pixel frames |
| Other GPUs | A100-40GB on Lambda, A10G (24 GB) on AWS g5 and Modal, H100 / L40S / L4 on Modal | A few clip chunks and speed comparisons (H100 at K=64: 4,154 tok/s) |
| Not used | B200 | Requested on Modal, never scheduled |

- **Model:** merged Qwen3.5-4B checkpoint (Qwenputer), bf16, about 18 GB on disk, 19.0 GB peak GPU memory.
- **Executor:** upstream Qwenputer Triton kernels with one CUDA graph per token, plus our K-token block verification (`--k-graph`, default 64) and fused kernels (`--fast-kernels`).
- **Guest build:** Apple clang 17.0.0 with `ld.lld` 17 (Homebrew clang 21 compiles but its objects do not link with lld 17). Python 3.12.10.
- **Media:** ffmpeg 7.1.1; animated SVGs rendered to GIF with headless Chrome through Playwright.
- **Parallelism:** Modal capped at 10 concurrent GPU containers; each model-decoded frame is split into 6 sub-segments run in parallel.
- Library versions (Torch, Triton, CUDA) are pinned in the Modal image and not listed here. Costs in this README are estimates, not billing data.

<a id="license"></a>

## 📜 License

QwenOS-original code is MIT, see `LICENSE`. The DOOM engine port (`ports/doomdmc/`,
`engine-patches/`, `apps/doomd*`) is built on DMC100-Doom, doomgeneric and DOOM, which are
GPL-2.0, see `COPYING`, so the built `/bin/doomd` image is GPL-2.0. Per-directory breakdown in
`NOTICE`. Freedoom is separate (BSD) and not included.

<a id="repo-map"></a>

## 🗺️ Repo map

| Path | What it is |
|---|---|
| `kernel/` | the QwenOS kernel (RV32IM) |
| `apps/` | shell and user programs, including doomd |
| `ports/` | the DOOM engine port (DMC100-Doom + Freedoom data) |
| `engine-patches/` | QwenOS edits to the engine |
| `tools/` | emulator, model drivers, chunk-ROM planner, regression scripts, readme_data.py |
| `tests/` | unit tests and frame/state goldens |
| `docs/` | ledgers, research notes, animations, optimization history |
| `docs/CLIP_LEDGER.md` | per-frame and per-chunk provenance of the 3-second clip |
| `docs/OPTIMIZATION_HISTORY.md` | earlier steps moved out of the README |
| `docs/readme/` | the long README sections, included verbatim by README.spec.yml |
| `README.spec.yml` | spec for video-readme-maker: README, charts and the explainer video |
| `video/` | qwenos_explainer.mp4, .srt, poster.png, preview.gif (generated) |
| `assets/` | generated hero, charts, diagram and GIFs |

---

<div align="center"><sub>Generated with video-readme-maker from README.spec.yml and the ledgers in docs/.</sub></div>
