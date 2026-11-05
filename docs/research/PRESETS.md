# Visual-quality presets for /bin/doomd (E1M1) -- TRADEOFFS, not equivalent computation

Host-emulator numbers only (`tools/rv32_fast.c`, `TOKCOST=1`). Nothing here ran on the model, GPU or any paid service.
Workload: E1M1 scripted demo (mode 2), 349 game tics, 15 of 35 tics drawn (15 fps, fixed for every preset), on top of
the LTO/Zba build of `perf/compiler`. Percentages are against the FULL preset (468,877 instr/tic, 689,070 tokens/tic).

**Labeling.** Every preset below except `full` makes the picture WORSE to make it cheaper. The game simulation (every
one of the 350 tics) is untouched: the per-tic lockstep state hash of `lite` and `fast` equals the one of `full`
(`tools/presets_golden.sh`). The pictures are not equal to FULL and must never be presented as equivalent output.
Roughly 138k instr/tic (29% of FULL's mean) is the simulation itself (median tic = a non-drawn tic); no render option can go below it.

## Shipped presets (`tools/mkdemo.sh PRESET`, `ports/doomdmc/lowres.sh NAME PRESET`)

| preset | what is reduced | instr/tic mean (median) | vs FULL | tokens/tic mean (median) | vs FULL | quality note |
|---|---|---|---|---|---|---|
| `full` (default, unchanged) | nothing | 468,877 (137,741) | 0 | 689,070 (194,650) | 0 | 160x200, status bar, light diminishing |
| `lite` | rows 0..39 black (letterbox), no status bar, no light diminishing | 411,570 (137,805) | -12.2% | 605,860 (194,703) | -12.1% | 160x160 picture, black bands top and bottom, HUD (ammo/health) gone, walls no longer darken with distance |
| `fast` | `lite` + 80 columns (each column drawn 2 px wide) | 280,418 (137,855) | -40.2% | 409,721 (194,768) | -40.5% | 80x160 picture: visibly blocky, vertical edges are 2 px stairs; same bands, no HUD, flat lighting |

Contact sheet (FULL / LITE / FAST, same frame): `docs/research/presets/contact_sheet.png`; single frames `full.png`, `lite.png`, `fast.png`.
Frame 40 is shown (320x240 canvas, 2x upscale).

## Exploration matrix (all at 15 fps, E1M1, 349 tics)

| variant (flags added to FULL) | instr/tic mean | vs FULL | tokens/tic mean | vs FULL | quality note |
|---|---|---|---|---|---|
| fixed light (`Q_FIXEDLIGHT=0`) | 459,577 | -2.0% | 678,996 | -1.5% | no distance darkening; barely visible in the lit E1M1 frame |
| no status bar (`Q_NOBAR`) | 450,937 | -3.8% | 666,497 | -3.3% | HUD removed |
| letterbox rows 40..199 (`Q_VTOP/VBOT`) | 437,622 | -6.7% | 637,246 | -7.5% | top 40 rows black |
| solid floors (`Q_SOLID=1`) | 459,759 | -1.9% | 661,273 | -2.1% | flats replaced by flat colour; small win, not shipped |
| 80 columns (`Q_DETAIL=2`) | 319,209 | -31.9% | 464,345 | -32.6% | blocky; biggest single lever |
| 80 columns + letterbox (existing `max`) | 302,878 | -35.4% | 437,437 | -36.5% | |
| 80 col + no bar + fixed light, no letterbox | 296,118 | -36.8% | 435,838 | -36.8% | |
| `fast` without fixed light | 284,822 | -39.3% | 414,605 | -39.9% | |
| `fast` + solid floors | 269,510 | -42.5% | 390,244 | -43.4% | flat floors on top of `fast`; not shipped |
| 320 columns (`Q_DETAIL=0`) | 761,237 | +62.4% | 1,128,521 | +63.8% | higher quality, more cost (reference) |

Not tried (need new engine code, not a build flag): skipping sprites/things, fewer texture rows, cheaper column modes beyond
the 80-column mode. Lower vertical resolution is not a build option today; the letterbox is the vertical lever.

## Rejected: lower draw rate (changes the demo)

Drawing fewer than 15 of 35 tics obviously helps (10 fps -27.6%, 7.5 fps -41.4%, 5 fps -55.7% instr/tic; tokens within 1 point of
that; drawing every tic is +109%), but it changes the demo, which stays at 15 fps. No preset is built around it.

## Reproduce

```
export DMC=<patched DMC100-Doom tree>        # engine-patches/ applied; E1.img under build/sw/nor/
make -s build/kernel-doomd.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf
tools/presets_measure.sh p_fast fast          # one preset: instr/tic and tokens/tic (per tic list in build/pm/NAME.tics)
tools/presets_matrix.sh; tools/presets_matrix2.sh; tools/presets_matrix3.sh   # the matrices above (build/pm/matrix*.txt)
tools/presets_report.sh                       # final numbers + frame PNGs (build/pm/png)
tools/mkdemo.sh fast                          # merged demo image with a preset (default stays `full`)
tools/presets_golden.sh                       # state + frame golden check of full / lite / fast (--update to adopt)
tools/doomd_regress.sh                        # default build regression (PASS, all hashes identical to tests/golden)
```

Goldens: `tests/golden/presets/{full,lite,fast}_frames.txt` (per-frame picture hashes, 100 tics) and `full_states.txt` (state
hash of the FULL lowres build, which `lite`/`fast` must match). These are separate from the regress goldens, because the
regress build draws every tic and its state hash diverges from a 15-of-35 build from tic 81 on (pre-existing, not from the presets).
`rv32_fast` now also prints a per-tic `tok` field in `TICLIST` output. Numbers are the host twin, not Qwen.
