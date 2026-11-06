# QwenOS DOOM demo: provenance ledger

Single source of truth for what each part of the demo video actually executed on.
Every agent that produces frames or model runs MUST append its rows here. No row, no claim.

## 1. Execution tiers (what "ran" means)

| Tier | Executor | Evidence |
|---|---|---|
| T0 | C emulator (tools/rv32_fast.c) | frames, instr counts |
| T1 | Python reference CPU / upstream `ref.Machine` | lockstep vs T0 (RAM image, console bytes, marker steps) |
| T2 | Qwen model (merged checkpoint, executor or HF path) with lockstep oracle | per-chunk verified: instr count match, BYTE tokens match, marker emitted, zero divergence |

A frame is "model-verified" only if it lies inside a T2 chunk that passed all checks.

## 2. Measured capability (fill in with measured, not estimated, numbers)

- Frames the OS can actually run per second/hour on T0: TBD
- Instructions per rendered frame / per skipped tic (E1M1, preset used): TBD
- Model throughput measured: tokens/s, instr/s per GPU type (A100, g5): TBD
- Max frames actually model-verified in a single uninterrupted run: TBD
- Max frames model-verified in total across all runs: TBD

## 3. Demo video assembly

- Target: 10 s at 15 fps = 150 rendered frames (game at 35 tics/s underneath)
- Number of separate model runs ("chunks") stitched together: TBD
- Chunk table (one row per chunk):

| Chunk | GPU/box | Start (tic/instr/key-schedule pos) | End | Frames emitted | Tokens | Wall time | Verified (Y/N) | Divergence | Log path |
|---|---|---|---|---|---|---|---|---|---|

- Frames in the video NOT model-verified (rendered by T0/T1 only): TBD
- Stitching method (snapshots from reference at chunk starts; pixels rendered from emulator, trace verified by model): TBD

## 3b. Quality decision (user, 2026-11-03)

- Every frame is rendered properly: use the FULL-quality preset (160x200 low-detail view, status bar, textured as available), NOT the 80-column/cropped 'max' preset.
- Frame rate is lowered instead: 15 rendered fps via skip pattern floor(t*15/35) (game logic every tic).
- Frames per model run is whatever a run can do; more runs/boxes make up the 5-10 s (75-150 frames). Document frames/run and run count here.
- Model runs do NOT use the serial pixel dump (pixels rendered by emulator from the same state; model verifies the trace + frame markers).

## 4. Disclosures (must appear in the final README)

- Disk is host-served block storage between segments (not inside the weights).
- Keyboard input is simulated/hardcoded by the host via the input mailbox, injected at step/event boundaries.
- Video pixels come from the emulator/reference; the model verifies the instruction trace (marker + lockstep), not pixel output.
- Clock is virtual (1 ms per idle call); not real time.

## Appended by video agent (T0 E1M1 gameplay video)

Section 2 (measured, T0 emulator, E1M1 skill 3, mode 2, scripted keys):
- 1060 game tics rendered and dumped (every tic, 320x240) in one uninterrupted T0 run: 5,457,271,471 instr total; frame 0 at 9.06M instr; per tic mean 5.14M / median 5.24M / min 3.72M / max 9.03M instr (frames 1..1059, includes Q_DUMP_ALL serial dump cost). rv32_fast ~250M instr/s => ~22 s CPU.
- ELF `qwenos-doomdmc-m2.elf` (copy: out/video/doomd-m2-dumpall.elf) md5 5030876bcc952c92cb04d1cbdeea26a7; disk E1.img md5 79b7d86efb58c3078d035a6736e38e3f; WAD freedoom1.wad md5 b93be13d05148dd01614bc205a03648e.

Section 3 (assembly): out/video/qwenos-doom-e1m1.mp4 (30.29 s, 35 fps, 1060 frames, 960x720) + .gif. Chunks: 1 T0 run, zero model chunks. Frames not model-verified: all 1060 (T0 only; not T1 lockstep-checked either). Key route: out/video/e1m1_route.keys (+ README table); uses debug keys T (tic 441) and g (tic 653); tics 2..440 are real keys only, so the first 10 s (tics 2..350) can be replayed by a model run unchanged. Disclosures 4 apply (host injects keys, virtual clock, disk host-served).

## 5b. Measured model runs (A100-SXM4-40GB, Lambda 129.146.78.123, Qwen3.5-4B merged 'rv1', executor path, lockstep oracle on)

| Run | Target | Instr | Chip tokens (model / planned) | Text tokens | Segments (disk pauses) | Frame markers | Model time | Verified | Divergence | Log |
|---|---|---|---|---|---|---|---|---|---|---|
| probe | model-probe ELF | - | 140 | 57 | 1 | n/a | ~s | Y | none | out/model (probe output in session) |
| title | title-frame (E1.img, marker 100->101) | 6,563 | 9,999 / 9,988 | 30 | 1 | 1 | 55 s incl. 31 s host prerun | Y | none | out/model/title.json |
| boot | cold boot -> first frame marker (title picture drawn) | 1,552,382 | 2,091,327 / 2,088,115 | 9,129 | 292 | 1 | 1,438 s (1,454 chip tok/s end-to-end) | Y (all 292 segments ok) | none | out/model/boot/boot.{json,log} |
