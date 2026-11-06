# 99 Things that did not work, and open gaps

Sources are the agent reports unless a file is named. "Tried" does not mean measured to the same standard as the numbered experiments.

## Dead ends
| Idea | What happened | Where |
|---|---|---|
| Vanilla doomgeneric | text 168 KiB fits ROM but RAM (bss about 240 KB, zone 6 MB) cannot | 04 |
| 1 MiB RAM in the model | about 1,024 DeltaNet heads of state; not a QwenOS change | 05 |
| Execute-from-RAM / runtime overlays | PC is anchored to ROM; overlays re-linked into ROM instead | 05, 07 |
| Prefetching 64-256 B on disk reads | reported as no useful gain (agent report; no trace kept, reason not recorded) | - |
| Random cache replacement | reported worse than LRU (agent report; no trace kept) | - |
| 16-byte record-cache lines at 32 sets / bigger caches | do not fit E1M7 skill 3 in plan B (RAM_BUDGET in ram.patch); 16 sets x 4 ways x 16 B measured best (5.01 M vs 5.38/5.19/5.25 M) | 12 |
| Strip width 16 | `Q_STRIPW=16` crashed at start (exit 99, 298,139 steps) in lowres batch 1; w8 same as base; ram.patch: w8 plan costs +10 % vs w16 | 14, 12 |
| Compression of baked data | reported no gain (agent report; no file evidence) | 17 |
| 80-column / cropped "max" preset for the video | cheap but looked bad; rejected for the video by decision on 2026-11-03 | 14 |
| `Q_NOBAR`, `Q_FIXEDLIGHT`, `Q_SOLID` as savings | each below 4 % | 14 |
| Bake as the main disk fix | E1M1 specific, uses the data ROM, replaced by chunk ROM | 17, 18 |
| Serial pixel dump on the model path | 78 k console bytes = 78 k full-Qwen text tokens per frame; pixels are rendered by the emulator instead | 20 |
| E4 maps that do not fit | E4M2, E4M6, E4M9: no RAM plan fits; E4M7 and E2M9: more than 8,191 segments | 13 |
| Intermission animations | not implemented; static statistics screens only | 13 |
| qsolid column reuse as first written | corrupted DEMO1 frame 202; fixed (+1.2 % instr) | 16 |

## Open gaps
1. No gameplay frame has run on the model (only probe, title-frame, boot-frame). Chunk ROM, key injection and the chunk driver are unexecuted on a GPU.
2. The 11 patches have not landed as one build: merge in `wt-merge` has failing hunks (os.patch on qlcd.c, qplat.c, rv32_fast.c) and a failing `doomd_regress` m1-states check from tic 57 (frames identical).
3. Chunk-ROM window (about 89 KB at 0x28C00) versus ROM flats (119.8 KB of 128 KiB used): unresolved in this record.
4. Upstream T1 lockstep for the full game: only 2.5 M instr checkpoints in the regress test and a 12 M instr dry run.
5. Throughput: the 3.7 k instr/s claim was not reproduced (about 1.08 k instr/s end to end on an A100).
6. Fleet (3 x g5) results unknown; hosts auto-terminate.
7. 5 s model-verified clip: not made (STATUS.md).
8. Disk, keys, clock are host-side (HONESTY.md).
