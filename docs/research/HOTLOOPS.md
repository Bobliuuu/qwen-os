# Hot-loop experiments on /bin/doomd (E1M1 demo)

All numbers are **host emulator** results (`tools/rv32_fast.c`, dynamic RV32 instructions and the `TOKCOST=1` chip-token model).
Nothing here ran on the Qwen model, a GPU or a paid service. Baseline = `origin/perf/compiler` (LTO + Zba, 164,509,698 instr,
238,221,788 tokens on `tools/compiler_bench.sh`, 350 game tics, host-served disk). Every kept change keeps the console md5
(`1b7e17987e2a839475b44ae635e1f03e`) and frame-buffer md5 (`2098581f19352ac314ee60ff2e1c28fd`) of the baseline and passes
`tools/doomd_regress.sh` (per-tic state hashes + frame hashes identical to `tests/golden`).

## Method

Dynamic profile with `tools/bbtrace` (merged from `perf/bbtrace`) on the bench ELF; call-site and argument histograms of
`R_ColumnLoop` and `rec_get` from a throw-away hook in a copy of rv32_fast (not committed). The engine tree is the DMC100 checkout
with `engine-patches/dmc100-qwenos-merged.patch` applied; this branch's engine changes are the delta
`engine-patches/dmc100-hotloops.patch` (apply after the merged patch, `patch -p1 -d $DMC < ...`).

## Result

| # | change | instr | vs perf/compiler | tokens | vs perf/compiler | hashes |
|---|---|---|---|---|---|---|
| 0 | perf/compiler baseline | 164,509,698 | 0 | 238,221,788 | 0 | ref |
| 1 | R_ColumnLoop: texel-run fill for magnified columns (kept) | 152,008,307 | **-7.60 %** | 211,239,743 | **-11.33 %** | identical, regress PASS |

Cumulative vs perf/compiler: **-7.60 % instructions, -11.33 % tokens**. Versus the original -O2 build (180,550,104 / 259,039,303):
-15.8 % instructions, -18.4 % tokens. Regress cost lines: DEMO1 -7.5 % instr/tic, E1M1 scripted -9.1 % instr/tic vs the old perf baseline file.

## 1. Run-length fill of magnified wall columns (kept)

Finding: of 4.5 M wall pixels, 3.8 M (84 %) are in columns where a texel covers 4+ pixels (step <= 0.25 texel/pixel; the demo
looks at near walls, mip level 6 bits, 0.04-0.14 texel/pixel). The old Duff loop spends 7 instr (srl, add, lbu, add, lbu, sb,
add) and a 4-token `sb` per pixel regardless. New `col_runs` (`port/render/r_inner.c`): per texel one src and one colormap
lookup, run length k = ceil((2^sh - frac) / step) clamped to the pixels left (exactly where the per-pixel stepping crosses the
texel boundary since step < 1 texel), then align with byte/halfword... in the committed version: byte loop to a 4-byte boundary,
`sw` of `c*0x01010101` words (1 token each instead of 4), byte tail. Columns with a larger step keep the Duff loop.

Reproduce: `DMC=<tree with both patches> tools/compiler_bench.sh NAME` (prints steps, tokens, md5, fbmd5), then
`DMC=... tools/doomd_regress.sh` (PASS).

## Experiments that were measured and dropped

| variant | instr | tokens | verdict |
|---|---|---|---|
| run fill threshold step <= 0.5 texel (instead of 0.25) | 153,361,982 | 212,597,592 | worse: short runs cost more than Duff |
| run fill threshold step <= 0.125 texel | 151,918,354 | 212,284,110 | -0.09 M instr but +1.0 M tokens: rejected (tokens count) |
| head/tail with halfword stores + `k<7` byte path | 152,307,506 | 211,474,849 | worse than the byte head/tail loops |

## Analysed, not implemented (no time inside the window)

* Duff column loop at 7 instr/pixel is at the minimum for the two-table lookup (shift, add, lbu, add, lbu, sb, step); packing
  4 pixels into a word costs 2 extra ALU instr per pixel and more tokens (slli/or values are 2-3 tokens, sb is 4).
* `rec_get` (7.4 %): 267 k calls, ~42 instr each, callers spread over R_DrawStrip, P_CrossSubsector, P_CheckSight, doomd_main;
  no single call site dominates. The hit path is already a leaf with 4 tag compares + LRU byte; maybe 1 % from dropping the LRU
  update, not tried. Enlarging the 64-line cache is blocked by the converter's baked arena plan (RC geometry feeds mklayout).
* `rc_fill`/`nor_read`/`nor_hw` (~11 %): the host-served mailbox protocol of the dry run; the production chunk-ROM path replaces it.
* R_SpanLoop (4.7 %, 10 instr/pixel, floors are minified so the run trick does not apply); per-span setup (5 FixedMul per span)
  could be memoised per (plane, row) but needs RAM and was not measured.
