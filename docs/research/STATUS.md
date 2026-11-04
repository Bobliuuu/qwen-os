# Status

Last refreshed: 2026-11-04 (merged build section updated; model-run sections still describe the pre-merge builds).

## Earlier state (per-patch builds, before the merge; kept for the record)
| Item | State |
|---|---|
| Main repo `<WORKDIR>/bundle/repo` | v0.12 README; git HEAD `a10465d`; working tree has uncommitted edits by other agents to many source files (Makefile, kernel, linker, apps, include, tools incl. `chunkrom.py`, `model_doom_qwen.py` with `--rom-plan`, `model_doom_chunks.py`); which of the 12 patches are fully in it was not audited. The v0.11-era `tools/rv32_fast.c` there lacks the `-s/-F/-W/-L` options |
| Patches (12 files) | in `<WORKDIR>/patches/` and copied to TRACES/patches with md5 |
| Merge tree `wt-merge` | in progress: os.patch has rejects in `qlcd.c`, `qplat.c`, `rv32_fast.c`; `doomd_regress`: frames and m2 states match golden, m1 state hashes differ from tic 57 (139/260 lines); mean 3.09 M instr/tic (m1), 3,618 req/tic. `make check` in the merge tree: one read of `out/check.log` ended with `make: *** [check] Error 1`, a later read of the (still-rewritten) file showed the boot test PASS and no verdict; treat as unknown. The copy in TRACES/merge/check.log is a snapshot |
| Floors variants measured in the merge tree (`fl-*.sum`) | fl-all 458.6 M / 335,774 req; fl-map 458.6 M / 335,770; fl-none 460.5 M / 340,890; fl-off 460.4 M / 340,890 (350 tics) |
| Model runs | probe, title, boot passed on A100; nothing else |
| Fleet | 3 x g5.xlarge launched; results unknown |

## Final merged build (refreshed from MERGE_NOTES.md at the repo root)
Everything below is emulator (T0) / reference (T1) evidence. The merged build has not itself been run on the model.
| Field | Value |
|---|---|
| Scope | E1M1 only (no bosses, episodes, sound or saves) |
| `make check` | green (kernel, layout, Python reference, 65 unit tests); one test (`test_key_inside_a_segment_is_refused`) is `expectedFailure` until `tools/model_doom_qwen.py` is updated to the key-ring protocol |
| `tools/doomd_regress.sh` | PASS against the original goldens (m1/m2 states and frames identical) |
| Lockstep | rv32_fast == Python reference == upstream `ref.Machine` for 6,000,000 instructions (level load + 2 frames); the whole 350 tics were not run on the Python references |
| Clean-rebuild md5 | `qwenos-e1m1.elf` bca0d1ad41c3f0571b349b588f12a3ee, `E1.img` 6287a13cc1079b697e1885f8f6327e06 |
| First E1M1 frame | 2,931,397 instr (no chunk ROM), 3,417,725 instr (chunk ROM) |
| Mean instr per game tic (tics 30-300, FULL preset) | 485,801 (host-served disk), 538,573 (chunk ROM) |
| Total, 350 tics FULL | 180.5 M instr (165,054 disk requests) or 199.7 M instr with chunk ROM (4 requests, 0 inside doomd) |
| Chunk-ROM plan | 5 chunks at frame markers 0-4, 4-17, 17-31, 31-100, 100-152; window 0x29000..0x3f000 |
| doomd stack high-water | 960 B of 1,408 B reserve |
| Model chunks run on the merged build | none |

Correction to older numbers in this folder: the chunk ROM costs +10.6 % instructions in the merged build (earlier notes say about 6.6 %).

## 5-second clip: pending
| Field | Value |
|---|---|
| Target | 5 s at 15 fps = 75 rendered frames, full-quality preset (PROVENANCE 3b) |
| Frames model-verified | pending |
| Frames emulator-only | pending |
| Chunks / GPUs / total wall time | pending |
| Published file and md5 | pending |
| Disclosures attached (HONESTY.md) | pending |
