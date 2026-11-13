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
