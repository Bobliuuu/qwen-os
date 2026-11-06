# Status

Last refreshed: 2026-11-03/04 (first version). Refresh this file when the merge lands.

## Current known state (per-patch builds, not merged)
| Item | State |
|---|---|
| Main repo `/Users/jhome/qwenos-work/bundle/repo` | v0.12 README; git HEAD `a10465d`; working tree has uncommitted edits by other agents to many source files (Makefile, kernel, linker, apps, include, tools incl. `chunkrom.py`, `model_doom_qwen.py` with `--rom-plan`, `model_doom_chunks.py`); which of the 12 patches are fully in it was not audited. The v0.11-era `tools/rv32_fast.c` there lacks the `-s/-F/-W/-L` options |
| Patches (12 files) | in `/Users/jhome/qwenos-work/patches/` and copied to TRACES/patches with md5 |
| Merge tree `wt-merge` | in progress: os.patch has rejects in `qlcd.c`, `qplat.c`, `rv32_fast.c`; `doomd_regress`: frames and m2 states match golden, m1 state hashes differ from tic 57 (139/260 lines); mean 3.09 M instr/tic (m1), 3,618 req/tic. `make check` in the merge tree: one read of `out/check.log` ended with `make: *** [check] Error 1`, a later read of the (still-rewritten) file showed the boot test PASS and no verdict; treat as unknown. The copy in TRACES/merge/check.log is a snapshot |
| Floors variants measured in the merge tree (`fl-*.sum`) | fl-all 458.6 M / 335,774 req; fl-map 458.6 M / 335,770; fl-none 460.5 M / 340,890; fl-off 460.4 M / 340,890 (350 tics) |
| Model runs | probe, title, boot passed on A100; nothing else |
| Fleet | 3 x g5.xlarge launched; results unknown |

## Final merged build: pending
| Field | Value |
|---|---|
| Merge commit / tree | pending |
| `make check` tests passed | pending |
| `doomd_regress` result and goldens | pending |
| ELF md5 / image md5 | pending |
| First E1M1 frame instr; mean instr per game tic; requests per tic | pending |
| Chunk-ROM plan for the merged build | pending |
| Model chunks run (table: GPU, range, instr, tokens, wall, divergence) | pending |

## 5-second clip: pending
| Field | Value |
|---|---|
| Target | 5 s at 15 fps = 75 rendered frames, full-quality preset (PROVENANCE 3b) |
| Frames model-verified | pending |
| Frames emulator-only | pending |
| Chunks / GPUs / total wall time | pending |
| Published file and md5 | pending |
| Disclosures attached (HONESTY.md) | pending |
