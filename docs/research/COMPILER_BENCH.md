# Compiler configuration bench for /bin/doomd (real DMC100 DOOM)

All numbers are **host emulator** results (instruction counts of the C twin `tools/rv32_fast.c`).
They are NOT Qwen speedups: nothing here was run on the model.

Workload: E1M1 scripted demo (mode 2), FULL preset (15 of 35 tics drawn), 350 game tics, chunk-ROM build
flags (rodata must fit `0x21000..0x29000`), host-served disk (same path as the dry run of `tools/mkdemo.sh`).
Baseline = the previous build (`-O2`, relax, gc-sections): **180,550,104 instructions**, 259,039,303 chip tokens.

Metrics

* steps: dynamic RV32 instructions of the whole run (primary).
* tokens: chip tokens from an exact per-record model (`TOKCOST=1` in rv32_fast; rules of `chipformer/rv/spec.py` and
  `ref.py`: 1-3 tokens per value by size, NT/J 1, SW 1, SB/SH 4, DIV QS + QD*(8-k0) + value, R refresh every 63
  commits). Checked against the official `ref.Machine`: 3,000,000 instructions = 4,212,306 tokens (+1 GO token
  upstream), identical. Baseline 1.4347 tokens/instr.
* text: `.text` bytes (limit 225,280 = ROM 0x41000..0x77fff); ro: `.rodata` (limit 32,768 with the chunk ROM at 0x29000).
* hash: console md5 (whole marker stream) and the 151 frame-buffer hashes equal to the baseline run. The winner also
  passes `tools/doomd_regress.sh` (per-tic state hash, DEMO1 260 tics + E1M1 100 tics, frame hashes, prod-vs-check):
  all identical to `tests/golden`.

## Result

Best: **LTO + Zba + hot objects -O3 / cold objects -Os + inline threshold 300** (now the default of
`ports/doomdmc/build.sh`; `TUNED=0` gives the old build).

* instructions 180,550,104 -> 164,509,698 (**-8.88 %**, `mkdemo.sh full` dry run); tokens 259.04 M -> 238.22 M (**-8.04 %**).
* regress cost lines: DEMO1 -8.2 % instr/tic, E1M1 -7.0 % instr/tic. State and frame hashes identical to the goldens.
* text 206,396 B (was 171,448; 18,884 B ROM headroom), rodata 30,564 B (was 32,096), bss 4,120 B (was 4,328).

## Matrix (every valid run; flags are deltas to the baseline; vs base = steps)

| config | steps | vs base | tokens vs base | text | rodata | hash | note |
|---|---|---|---|---|---|---|---|
| base (-O2, relax, gc) | 180,550,104 | 0 | 0 | 171,448 | 32,096 | ok | |
| -Os | 184,278,610 | +2.07% | +1.95% | 148,684 | 31,476 | ok | smaller, slower |
| -Oz | 201,344,159 | +11.52% | +8.82% | 133,752 | 31,500 | ok | |
| -O1 | 183,361,771 | +1.56% | +1.26% | 166,844 | 32,312 | ok | |
| -O3 | 179,616,447 | -0.52% | -0.49% | 182,724 | 32,096 | ok | |
| -O3 + inline 500 | 179,378,375 | -0.65% | -0.61% | 196,508 | 32,096 | ok | |
| -O2 -fno-unroll-loops | 181,777,187 | +0.68% | +0.54% | 165,188 | 32,312 | ok | worse |
| -O3 -fno-unroll-loops | 180,938,626 | +0.22% | +0.09% | 169,508 | 32,312 | ok | worse |
| -O2 unroll-threshold 400 | 180,319,637 | -0.13% | -0.10% | 178,552 | 32,096 | ok | |
| -O2 -fno-vectorize -fno-slp-vectorize | 180,550,104 | 0 | 0 | 171,448 | 32,096 | ok | no vector unit on rv32im: no-op |
| -O2 inline 25 | 183,284,933 | +1.51% | +1.48% | 153,424 | 32,096 | ok | |
| -O2 inline 500 | 179,743,079 | -0.45% | -0.45% | 186,900 | 32,096 | ok | |
| -O2 inline 1000 | 178,068,791 | -1.37% | -1.09% | 199,880 | 32,260 | ok | |
| r_inner.c at -O3 / -O2 with unroll / -Os | 180,550,104 | 0 | 0 | ~same | 32,096 | ok | r_inner is hand unrolled; compiler flags do not change steps |
| -mno-relax, --no-relax | 194,134,616 | +7.52% | +6.19% | 190,844 | 32,096 | ok | gp-relative accesses lost |
| relax at compile, --no-relax at link | 194,134,616 | +7.52% | +6.19% | 190,844 | 32,096 | ok | same |
| no --gc-sections | - | - | - | - | - | BUILD FAILED | undefined symbols (myargc ...): unreferenced engine code needs symbols |
| -O2 + Zba | 177,628,993 | -1.62% | -1.12% | 168,784 | 32,096 | ok | sh1add/sh2add/sh3add |
| -O3 + Zba | 176,775,358 | -2.09% | -1.58% | 179,848 | 32,096 | ok | |
| -O2 -flto | 168,968,166 | -6.41% | -5.89% | 199,780 | 30,748 | ok | |
| -O2 -flto + Zba | 166,030,468 | -8.04% | -7.02% | 195,732 | 30,748 | ok | |
| -O3 -flto | - | - | - | - | - | BUILD FAILED | .text overflows the ROM region by 18,796 B |
| -O3 -flto + Zba | - | - | - | - | - | BUILD FAILED | overflows by 13,492 B |
| -O2 -flto, --lto-O3 | - | - | - | - | - | BUILD FAILED | overflows by 9,096 B |
| -O2 -flto, inline 500 / 1000 | - | - | - | - | - | BUILD FAILED | overflows (83,644 B at 500) |
| -O2 -flto, inline 150 | 170,267,441 | -5.70% | -5.38% | 180,368 | 30,748 | ok | |
| -O2 -flto -fno-unroll-loops | 170,079,193 | -5.80% | -5.49% | 190,344 | 31,268 | ok | |
| -Os -flto | 174,875,981 | -3.14% | -2.82% | 137,960 | 31,096 | ok | |
| -O3 (frontend) -flto, --lto-O2 | 168,682,017 | -6.57% | -6.24% | 212,568 | 30,732 | ok | |
| -O3 (frontend) -flto + Zba | 165,828,444 | -8.15% | -7.35% | 208,328 | 30,732 | ok | |
| -O2 -flto + Zba, hot objects -O3 | 165,812,157 | -8.16% | -7.36% | 198,048 | 30,748 | ok | |
| ... + cold -Oz | 167,526,236 | -7.21% | -6.57% | 138,364 | 30,632 | ok | frees ROM for inlining |
| ... + cold -Oz, hot -O2 | 167,776,417 | -7.07% | -6.33% | 135,940 | 30,632 | ok | |
| ... + cold -Oz, --lto-O3 | 166,090,447 | -8.01% | -7.18% | 147,972 | 30,664 | ok | |
| ... + cold -Oz, hot -fno-unroll-loops | 168,468,263 | -6.69% | -6.15% | 136,592 | 30,668 | ok | |
| ... + cold -Oz, --relax without --relax-gp | 179,313,559 | -0.68% | -2.07% | 147,388 | 30,632 | ok | gp window matters (~7.5 points) |
| ... + cold -Oz, inline 200 | 166,716,801 | -7.66% | -6.88% | 158,888 | 30,444 | ok | |
| ... + cold -Oz, inline 300 | 165,211,862 | -8.50% | -7.79% | 181,280 | 30,444 | ok | |
| ... + cold -Oz, inline 350 | 168,008,543 | -6.95% | -5.93% | 186,616 | 30,516 | ok | inlining is chaotic, not monotone |
| ... + cold -Oz, inline 400 | 167,806,569 | -7.06% | -5.98% | 194,716 | 30,476 | ok | |
| ... + cold -Oz, inline 450 | 166,578,680 | -7.74% | -6.78% | 220,988 | 30,508 | ok | near the ROM limit |
| ... + cold -Oz, inline 500 / 1000 / 2000, 500 + lto3, 500 + unroll | - | - | - | - | - | BUILD FAILED | ROM overflow (4,080 B at 500) |
| ... + cold -Oz, inline 300, no Zba | 168,189,816 | -6.85% | -6.65% | 183,700 | 30,444 | ok | Zba is worth 1.7 points on top of LTO |
| ... + cold -Os, inline 300 (first default, G_Ticker inside LTO) | 164,587,533 | -8.84% | -8.05% | 204,996 | 30,468 | ok | |
| **default: same, g_game.c built without LTO** | **164,509,698** | **-8.88%** | **-8.04%** | 206,396 | 30,564 | **ok, regress PASS** | winner (g_game is kept out of LTO so rv32_fast still finds G_Ticker for per-tic stats) |
| default with cold -Oz | 165,166,276 | -8.52% | -7.80% | 182,236 | 30,540 | ok | 24 KB less text, 0.4 points less |
| default with hot -O2 | 165,106,735 | -8.55% | -7.50% | 203,384 | 30,564 | ok | |
| default with hot -fno-unroll-loops | 165,447,146 | -8.36% | -7.63% | 203,368 | 30,600 | ok | |
| default + `--symbol-ordering-file` hot-first and hot-last (dynamic PC profile order) | 164,509,698 | 0 vs default | 0 | 206,396 | 30,564 | ok | no instruction effect, see below. Caveat: these two runs may not have applied the file (output byte-identical to default); treat as "no measurable effect", unverified |

Early runs that passed `EXTRA_CF` produced nothing, because `lowres.sh` overwrote `EXTRA_CF`; they were discarded and
re-run after the fix. The rows above are the valid ones.

## Findings and why

* Biggest lever is LTO (-6.4 %): cross-file inlining of the cache (`rec_get`), fixed-point and drawer helpers. It
  needs ROM: plain `-O3` or large inline thresholds overflow the 225,280 B code region, so cold objects are built `-Os`
  (-Oz saves another 24 KB but costs 0.4 points) and hot objects (profile list in `build.sh`) `-O3`.
* Zba (`sh1add/sh2add/sh3add`) is implemented by the Qwenputer core (`core.py`: "RV32IM + Zba"; `ref.py` ZBA ops) and
  is worth about -1.6 %. **Zbb is not implemented** (no min/max/clz/rotate), so no `-march=..._zbb`.
  `tools/rv32_fast.c` now decodes the three Zba ops (it did not before); `tools/rv32_qwenputer.py` was not changed.
* gp relaxation matters: without `--relax-gp` the tuned build loses ~7.5 points; `-mno-relax` is +7.5 % vs base.
* The hand-unrolled `R_ColumnLoop` is already 7 instr/pixel (srl, add, lbu, add, lbu, sb, add) and clang emits exactly
  that; no hand specialization that stays hash identical was found. It is ~20 % of all instructions, then R_DrawStrip
  (inlined walls/planes) 18 %, R_MapPlane 9 %, `rec_get` 7.5 % (profile of the Zba+LTO build, `PROF=1 PTOP=45`).
* Function ordering from the PC profile cannot change instruction count: no I-cache, all calls reach `jal`.
  Not adopted. Hand-specialized loops and per-function pragmas in qsolid/qlcd/fastfix/ovl_rv were not attempted beyond
  the per-object hot -O3 (qsolid, qlcd, fastfix, ovl_rv are in the hot list).
* Per-opcode token weights: DIV/REM cost 1 + (8-k0) + value tokens (232,133 divisions = 1.31 M tokens, 0.5 % of the
  baseline total); SB/SH stores 4 tokens, SW 1; values beyond +-16K cost 2-3 tokens; MUL costs like ALU.
  Tokens fall ~0.8 points less than instructions because the removed instructions are mostly cheap 1-token ops.

## Not verified / caveats

* Instruction counts only. No model run, no wall-clock, no GPU.
* `tools/mkdemo.sh`'s last step ("verification run with the chunk ROM") exits 99 (`DOOM.DAT not usable`) in this
  environment for the unmodified baseline as well (pre-existing here, not caused by this change); chunk-plan
  generation and the dry run work, and the tuned demo rodata (0x7764) fits the 0x8000 window.
* The 3-way upstream lockstep test (`tests.test_doomd_regress`) was not rerun; the Python reference tools do not
  implement Zba, so the Python-ref comparison of a Zba build needs the upstream `chipformer.rv.ref` (which does).
* Engine tree used: upstream 0cdc78e + `engine-patches/dmc100-qwenos-merged.patch`, Apple clang 17 + swiftly ld.lld,
  E1.img md5 6287a13cc1079b697e1885f8f6327e06.

## Reproduce

```
# engine tree: upstream 0cdc78e + engine-patches patch, with build/sw/gen and build/sw/nor/E1.img
export DMC=<path>/DMC100-Doom
make build/kernel-doomd.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf
tools/compiler_bench.sh tuned                         # new default
TUNED=0 tools/compiler_bench.sh plain                 # old -O2 build (baseline)
TUNED=0 OPT="-O2 -flto" LDX="--lto-O2" ARCHX=_zba tools/compiler_bench.sh lto-zba     # any row: OPT, ARCHX, LDX, HOT/HOT_CF/COLD_CF, INNER_CF
tools/doomd_regress.sh --clean                        # state/frame hashes vs tests/golden
tools/mkdemo.sh full                                  # production-style image + dry-run steps
TOKCOST=1 build/rv32_fast <elf> <E1.img> 154 15c out.bin 4000000000   # chip-token model
```

Knobs of `ports/doomdmc/build.sh`: `TUNED, OPT, ARCHX, INNER_CF, HOT, HOT_CF, COLD_CF, INLINE_T, CF_<object>, GCFLAG,
LDRELAX, RELAXFLAG, LDX`.
