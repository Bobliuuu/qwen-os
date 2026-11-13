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
