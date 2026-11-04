# TRACES: small evidence files

Total size about 1.2 MB (budget 20 MB). No ELFs, images, mp4/gif, or raw request logs are copied; originals are under `<WORKDIR>/` (md5s in patches/PATCH_MD5.txt).

| Path | What | Used by |
|---|---|---|
| PROVENANCE.md | execution-tier ledger (T0/T1/T2), measured model runs, disclosures | all |
| RAM_BUDGET_v1.txt | final v1 RAM/ROM budget (before ram.patch) | 06, 12 |
| model/title.json, boot.json, boot.log.gz | real-model run reports (A100) incl. per-segment detail | 20 |
| model/merge.log | circuit shape and weight loading log | 05, 20 |
| full/results.txt, episodes.txt, *.keys | 15 feature PASS lines, 4-episode results, key scripts | 13 |
| lowres/lr_batch1.txt, lr_batch2.txt, lr_batch2.sh, lr_run.sh | 350-tic sweep logs and scripts | 14 |
| perf/profile_phase2_prof2.txt, v0long_baseline_frames.log.gz, cmp.py, fh.py, verify.sh, prof.sh | instruction profile, original per-frame deltas, equivalence tooling | 09 |
| chunkrom/rom_plan.json, dry_rom.json, dry_norom.log, analyze.py | 5-chunk plan, dry runs, request-analysis script | 18 |
| merge/*.sum, regress1.log, check.log, os-apply.log, mk.sh, tics.sh | in-progress merge evidence | STATUS, 15, 16 |
| video/VIDEO_README.md, e1m1_route.keys | video provenance and key route | 19 |
| patches/*.patch, PATCH_MD5.txt, golden_*.txt, ram-NOTE.txt, test.notes.txt | all 12 patches (copies) with md5s; golden notes | all |
| frames/01..15 *.png | 15 representative frames | below |

Frames (all T0 emulator output, none model-verified):
| File | Shows |
|---|---|
| 01_bsp_viewer_freedoom_e1m1 | v0.12 32x24 BSP viewer |
| 02_dmc_demo1_frame | DMC100 port, DEMO1 (first working engine frames) |
| 03_e1m1_tic30_flatcolour_floors_v1 | E1M1 tic 30, port v1 |
| 04_ram_before_flatcolour / 05_ram_after_textured | ram.patch before/after, E1M1 tic 40 |
| 06_lowres_full_160x200_skip15 | the "full" preset |
| 07_lowres_preset_balanced / 08_lowres_preset_max | balanced and max presets |
| 09_lowres_80col_crop60 | 80-column cropped variant (rejected) |
| 10_full_title, 11_full_door_open, 12_full_ep1_m1, 13_full_ep4_spider_spawn, 14_full_intermission, 15_full_finale_text | full-game checks |

Not copied (too large or not needed): `out/video/*.mp4|gif`, `ram-E1.img` (4 MB), the ELFs, `wt-chunkrom/out/*.bin` request logs (2.5-4.8 MB each), `engine/port/van_qos.elf.map` (527 KB), full frame sets in `out/full` (39 MB).
Missing evidence: raw upstream boot log (120,267 instr), probe run output (only the ledger row), per-run perf logs for sys/render, bake request-analysis tables (the 95 % figure), the 165,054-request chunk-ROM before/after tables, model-run host command line.
