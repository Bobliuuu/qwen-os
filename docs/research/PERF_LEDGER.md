# Performance ledger: model-verified execution speed

Every row is a **measured** number from a Modal run on 2026-11-04 (A100-40GB list price about $2.10/h) unless marked otherwise. "Verified" means the driver's lockstep oracle compared every predicted chip token with the reference machine and the run exited with no divergence. Chip execution is fully in-weight (compiled circuit, Triton executor); the 30-token tool-call turn per segment is the hybrid part (Qwen text layers).

Harness: `tools/model_doom_qwen.py` (driver), `tools/kgraph.py` (K-token blocks), `tools/exec_microbench.py` (E1), `tools/text_cost_probe.py` (E4). Chunk c34 of the published plan = segment 38:39, 1,090,708 instructions, 1,575,918 chip tokens, checkpoint `q4-rv1`, executor path, patched (deque) upstream `chat.py`. Modal image: torch 2.14.1, flash-linear-attention 0.6.0.

## E1: where does the per-token time go (microbench, 20,000 teacher-forced tokens, circuit built from `core.build`, no checkpoint)

| GPU | A graph only (us/token) | B host loop as the driver does it (us/token) | C K=16 tokens per graph (us/token) |
|---|---|---|---|
| A100-40GB | 242.3 | 283.1 | 241.9 |
| A10G | 318.9 | 372.0 | 318.6 |
| L4 | 192.9 | 238.8 | 193.3 |
| L40S (6,000 tokens) | 164.7 | 185.5 | 166.5 |
| H100 (6,000 tokens) | 203.4 | 225.2 | 204.7 |

Reading: host loop adds 15-24% over the graph; putting K tokens in one graph does not make the graph itself faster (C equals A). The GPU kernels are the floor. Rate does not track GPU class: L4 and L40S are faster than A100 and H100 on this load (latency-bound tiny kernels, clocks). A100 profile (200 tokens, torch profiler): `_head_kernel` 10 launches/token, 15.9 us each = 50% of kernel time; `_ffn_kernel` 10 launches, 10.1 us = 32%; `_apply_kernel` 20 launches, 2.4 us = 15%.
Correctness note: the microbench feeds the plain full-ROM trace, so it reports 283 "mismatches" after token 971 on every GPU, identically. That is a microbench artifact (the real driver uses the chunk-ROM window and has zero), not a model error; the timing numbers are not affected. It is not used as an exactness claim anywhere.

## E3: K-token CUDA graph with bulk lockstep verification, real driver, chunk c34

Baseline = the same driver with `--k-graph 0` (old per-token loop), same GPU type, same chunk, same verify mode. All rows: 0 lockstep errors, 0 slow (re-decoded) blocks, head mismatches reported by the driver 0.

| GPU | change | model seconds | chip tok/s | instr/s | vs baseline | status |
|---|---|---|---|---|---|---|
| A100-40GB | baseline K=0 | 705.6 | 2,233 | 1,546 | 1.00x | baseline |
| A100-40GB | K=16 | 479.4 | 3,287 | 2,275 | 1.47x | superseded |
| A100-40GB | K=64 | 463.6 | 3,399 | 2,353 | 1.52x | **kept, default** |
| A100-40GB | K=256 | 459.3 | 3,431 | 2,375 | 1.54x | no real gain over 64 |
| A100-40GB | K=64 + pipelined launch (`--k-pipe`) | 492.9 | 3,198 | 2,213 | 0.94x vs K=64 | reverted (flag off by default, host is no longer the bottleneck) |
| A100-40GB | K=128 + pipelined launch | 462.7 | 3,406 | 2,357 | 1.00x vs K=64 | no gain |
| H100 | baseline K=0 | 606.1 | 2,600 | 1,800 | 1.00x | baseline |
| H100 | K=64 | 379.4 | 4,154 | 2,875 | 1.60x | kept |
| A10G | baseline K=0 | 746.1 | 2,112 | 1,462 | 1.00x | baseline |
| A10G | K=64 | 582.5 | 2,706 | 1,873 | 1.28x | kept |

GPU memory peak (torch max allocated): 19.0 GB in all K settings (K=0 18.99 GB, K=64 19.02 GB, K=256 19.02 GB).
Mechanism: K=64 removes 2 device-to-host syncs and the Python decode per token; the oracle's tokens are known, so the K inputs are staged at once and the K outputs are compared on the device (one sync per block). Exactness is by construction: a block that is not bit-identical to the oracle's codes is re-decoded token by token with the original rule and aborts at the first real divergence. Remaining gap to the graph-only floor on A100: 294 us/token at K=64 vs 242 us/token graph-only; pipelining did not close it, so it is GPU time (state-dependent kernels), not host.

## E4: text-token and per-segment cost (A100, executor path, warm)

| quantity | measured |
|---|---|
| ms per text token (full Qwen layers, batch 1, flash-linear-attention installed) | 45.0-45.1 (iteration 2 and 3), 47.9 first |
| fixed cost per segment before the first token (prefill + snapshot + executor start) | 0.21 s warm |
| one-time first-call cost (Triton compile, graph capture) | 51 s |
| chip tokens in that probe | 1,031 in 0.38 s (K=0 path, small sample) |

So a segment with about 30 text tokens costs about 1.6 s; 292 segments about 470 s. Measured with a synthetic calc-tool-call turn (the probe's chip run ends at the first bridge-stage divergence of its synthetic firmware; only the timing split is used).

## E2: other GPUs

Covered by the E1 and E3 tables above (A10G, L4, L40S, H100, A100), all through Modal, because the `lab` AWS session had expired. Rate scales weakly with GPU class: K=0 chunk rate A10G 2,112, A100 2,233, H100 2,600 tok/s.

## E5 (batched rows): not run. It only raises aggregate throughput, not single-stream speed; skipped for time.

## Triton executor kernels (exact), microbench then real driver

Patch: `tools/patches/tritonexec_fast.patch` (unified diff against upstream `chipformer/rv/tritonexec.py`; class attributes `SPLIT`, `FUSE`, `CH`, `GW`, `H2W`, `BLOCK`, `FW`, all defaulting to the old behaviour). Driver flag `--fast-kernels` sets SPLIT=True, CH=16, GW=4, H2W=4, BLOCK=4, FW=1, FUSE=True. Batch size 1 only (not tested for B>1).
Exactness evidence (microbench, A100, baseline and variants in one process, 20,000 teacher-forced tokens): `kout` (all kept dims) `torch.equal` at all 20,000 tokens, full residual sampled every 97 tokens equal, final S and history state equal; a second baseline run was identical too. Not run on other GPUs for exactness.

| A100 graph-only, us/token (each vs 242-245 baseline, same process) | us/token | status |
|---|---|---|
| head kernel num_warps 1 / 2 / 8 / 16 / 32 | 539 / 342 / 217.5 / 210 / 224 | num_warps=16: -13% |
| FFN BLOCK 16 / 128 / 256 | 232 / 277 / 1073 | BLOCK small is better |
| apply kernel num_warps | no gain | reverted |
| SPLIT (gather k/v/z/q in own kernel, 16-row programs) + FFN BLOCK=4 | 182 (-25%) | kept |
| SPLIT + FUSE (no apply kernels; the x += y add is folded into the next kernel's read, lag history move deferred) | 162.3 (-33%) | kept |

Real driver, chunk c34, A100-40GB, `--k-graph 64 --fast-kernels`, lockstep on:

| config | model seconds | chip tok/s | instr/s | vs baseline | lockstep errors / slow blocks |
|---|---|---|---|---|---|
| baseline (K=0, old kernels) | 705.6 | 2,233 | 1,546 | 1.00x | 0 / n.a. |
| K=64, old kernels | 463.6 | 3,399 | 2,353 | 1.52x | 0 / 0 |
| K=64 + fast kernels | 349.4 | 4,510 | 3,121 | **2.02x** | 0 / 0 |

Per-token on A100: 316 us (baseline) -> 294 us (K=64) -> 222 us (K=64 + fast kernels); graph-only floor of the fast kernels is 162 us, the rest is host work and state-dependent kernel time.

## Zba on the checkpoint

PASS (real model, lockstep, A100, `--k-graph 64`): combined ELF segments 1:4 run from reset, 255,094 instructions and 352,219 chip tokens, no divergence, 0 slow blocks; first SH?ADD at instruction ~90.2k and 9,399 SH?ADD executed in that window. A separately built tuned ELF (LTO, Zba, hot -O3) also ran 1.75M steps with 0 mismatches (47,925 SH?ADD executed). Note a build bug found on the way: `tools/chunkrom.py` on perf/compiler used CRX_BASE 0x28C00 while the guest uses 0x29000; a wrong plan base makes the reference and driver fault in `nor_read` at step ~90,380 right after the first sh3add, which looks like, but is not, a Zba failure.

## OLD vs COMBINED build

COMBINED_PENDING
