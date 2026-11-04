# Timeline

Times are file mtimes on 2026-11-03 (local) unless stated. Order of the numbered steps follows the files; the agent worktrees ran in parallel, so later patches were developed on trees that already had earlier ones.

| When | Step | Outcome | Experiment |
|---|---|---|---|
| before 17:53 | v0.9-v0.11: WAD viewer, v0.10 stack cut (22 KiB app RAM), emulator, 29 tests | baseline; upstream CPU never run | 01 |
| 17:53-17:59 | Real-WAD BSP viewer on Freedoom E1M1 (v0.12); 225-290 K instr/frame; 32 tests | worked, not DOOM | 02 |
| 2026-11-03 | Upstream `ref.Machine` boots QwenOS: 120,267 instr, about 173 k tokens; probe passes | worked | 03 |
| 17:56-18:02 | doomgeneric rv32im prototype in `engine/port` (map file 527 KB) | RAM no-go (bss about 240 KB, 6 MB zone) | 04 |
| about 18:00 | Qwenputer audit: spec.py constants, 1 MiB RAM rejected, exec-from-RAM rejected, speed claim noted | constraints | 05 |
| 18:11-18:16 | Takeover mode, repacked ROM, `RAM_BUDGET.txt` v1 (30.56 KiB app RAM) | worked | 06 |
| 18:12-18:21 | DMC100-Doom ported to RV32: ELF built, DEMO1 frames dumped (`out/doomd-demo1-0*.png`) | worked: 11.26 M first frame, 3.5 M/tic | 07 |
| 18:53 | Frames for E1M1 (`doomd-m2-*`), flat-colour floors; redraw skip, -O2, fastfix, qimg, qsolid | 6.19 M first frame, 5.14 M/tic | 08 |
| 18:52 | Full-game key scripts (`out/full/*.keys`) | | 13 |
| 18:53-19:05 | perf.patch: profiler, caches, inline disk read | 10.47 M -> 3.52 M per tic; 6,807 -> 2,195 req | 09 |
| about 19:05-19:24 | sys.patch (-7 %), render.patch (-18 %, gp relaxation) | worked | 10, 11 |
| 19:12-19:15 | GPU fleet launched (3 x g5, 2026-11-04 00:07 UTC); first A100 runs: probe, title-frame (19:13), merge log (19:00) | probe/title pass | 20, 21 |
| 19:24-19:25 | ram.patch: core 152 B, 88 flats in ROM, plans A/B, textured everywhere | worked (35 tests) | 12 |
| 19:27 | full.patch and full-engine.patch: keyboard fix, saves via DISK_WRITE, episodes; results.txt 15 PASS | E1 9/9, E2 8/9, E3 9/9 packed, E4 5/9 | 13 |
| 19:30-19:31 | lowres.patch; batch tables; presets; skip 15/35 | worked; 80-col rejected for video | 14 |
| 19:33-19:34 | T0 E1M1 gameplay video (1060 frames, 30.29 s) | done, T0 only | 19 |
| 19:38-19:43 | os.patch (live shell, key ring, KEY_WAIT, qwenos_live.sh); PROVENANCE ledger written | 3.73 M cold boot -> first frame | 15 |
| 19:40 | A100 cold boot -> first frame marker: 1,552,382 instr, 292 segments, 1,438 s | pass, zero divergence | 20 |
| 19:43-19:46 | test.patch: goldens, regress, qsolid root cause (DEMO1 frame 202) | bug fixed | 16 |
| 19:09-19:56 | bake.patch (95 % fewer requests), then chunkrom.patch + chunkrom-model.patch (19:54): 165,054 -> 4 requests, +6.6 %, 5 greedy chunks | bake shelved; chunk ROM host-verified | 17, 18 |
| 19:50-20:01 | Merge into `wt-merge`: os.patch hunks fail on 3 files; regress1: m1-states diverge at tic 57 | in progress | STATUS |

Gaps in the timeline: exact times of the parallel worktrees overlap; mtimes show copy time for several files (many `wt-*/base` files carry the same minute), so the order of 09-12 within 19:05-19:25 is approximate.
