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
