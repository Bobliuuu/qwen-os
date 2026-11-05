# perf/combined: compiler + hotloops + sim, measured together

All numbers are **host-emulator** results (`tools/rv32_fast.c`, dynamic RV32IM instructions and the `TOKCOST=1` chip-token model; E1M1 scripted,
FULL preset, 350 game tics, host-served disk = `tools/compiler_bench.sh`). Nothing here ran on the Qwen model, a GPU or a paid service.

## Contribution per branch (each step measured by its own branch doc, combined measured here)

| build | instructions | vs original | tokens | vs original | vs previous step (instr) |
|---|---|---|---|---|---|
| original (-O2, relax, gc-sections) | 180,550,104 | 0 | 259,039,303 | 0 | |
| perf/compiler (LTO + Zba) | 164,509,698 | -8.88 % | 238,221,788 | -8.04 % | -8.88 % |
| + perf/sim (strong memcpy/memset, FixedDiv fast path), measured alone on compiler | 162,660,912 | -9.90 % | 235,760,253 | -8.99 % | -1.12 % |
| + perf/hotloops (col_runs fill), measured alone on compiler | 152,008,307 | -15.80 % | 211,239,743 | -18.45 % | -7.60 % |
| **perf/combined (all three, measured here)** | **150,159,521** | **-16.83 %** | **208,776,718** | **-19.40 %** | -8.72 % vs compiler, -1.22 % vs hotloops alone |

The sim-alone and hotloops-alone rows are the numbers in docs/research/SIMLOGIC.md and HOTLOOPS.md; the sim-alone figure was reproduced exactly in this
environment while the hotloops engine patch was missing. The two gains do not add: combined vs compiler is -8.72 % instr, -12.36 % tokens.
Console md5 `1b7e17987e2a839475b44ae635e1f03e` and frame-buffer md5 `2098581f19352ac314ee60ff2e1c28fd` equal the baseline's (same picture and tic sequence).

Chunk-ROM production run of the same ELF (empty window excluded, ROM windows served, `tools/mkdemo.sh`): 167,878,494 instructions, only 4 disk requests in total.

## Clip (45 drawn frames, game tic 102, chunk ROM)

| | instructions | planned chip tokens (1.391 tok/instr) |
|---|---|---|
| published clip build | 81,065,587 | 112,762,231 |
| combined | 72,277,308 | 100,537,735 (-10.8 %) |

## ROM and RAM

* text 209,292 B of 225,280 B: **15,988 B headroom** (compiler 206,396; the sim memcpy/FixedDiv code adds ~2.5 KB, the col_runs path ~0.4 KB).
* rodata 30,564 B (must fit 0x21000..0x29000 = 32,768 B: 2,204 B free), data 52 B, bss 4,120 B. Chunk-ROM windows (0x29000..0x3f000) are 74-88 KB-ish
  of the 90,112 B available: `chunk markers ... OK` for all 5 ROM chunks. No RAM-layout change.

## Correctness

* `tools/doomd_regress.sh --clean`: PASS. m1 (DEMO1) and m2 (E1M1 scripted) per-tic state hashes and per-frame hashes identical to `tests/golden`
  (also for a build without hash code); cost lines: DEMO1 -8.7 %, E1M1 scripted -10.4 % instr/tic vs the old perf baseline file.
* `make check`: exit 0.

## Chunk-ROM verification fix

`tools/mkdemo.sh` ended with exit 99 ("DOOM.DAT not usable", img_init -> 1) in the CRX verification run, also on the baseline. Cause: `tools/chunkrom.py`
had `CRX_BASE = 0x28C00` while the guest (`Q_CRX_BASE`, lowres.sh) and rv32_fast (`CRXBASE=29000`) use `0x29000`, so every ROM address in the plan was
0x400 too low and the first ROM-served read returned wrong bytes. Fixed to 0x29000. `make demo-elf` now verifies: chunk reads 2/0/0/0/0, `DISK total_req=4`, exit 0,
151 frames. (Not the cause: image layout. The `E1.img` packed by `tools/fetch_engine.sh` with `QFLAT_SLOTS=0` does not match the regress/demo builds
(DEMO1 produces no frames, E1M1 frame hashes differ); the image that passes regress and matches the published clip is md5 6287a13cc1079b697e1885f8f6327e06.
That is a separate pre-existing issue, not fixed here.)

## Reproduce

    git checkout perf/combined
    # engine: DMC100-Doom 0cdc78e + both patches (apply in this order), E1.img md5 6287a13c... at $DMC/build/sw/nor/E1.img
    patch -p1 -d $DMC < engine-patches/dmc100-qwenos-merged.patch
    patch -p1 -d $DMC < engine-patches/dmc100-hotloops.patch
    export DMC=...  # riscv clang + lld 17 (Apple/swiftly toolchain worked; clang 21 objects do not link with lld 17), llvm-nm on PATH
    tools/compiler_bench.sh combined      # steps=150159521 tokens=208776718, text=209292
    tools/doomd_regress.sh --clean        # PASS
    tools/mkdemo.sh                       # build/demo/qwenos-e1m1.elf + crx-plan.{bin,json}; CRX chunks reqs=2/0/0/0/0, total_req=4
    python3 tools/model_runplan.py --elf build/demo/qwenos-e1m1.elf --kernel-elf build/kernel-doomd.elf --disk $DMC/build/sw/nor/E1.img \
      --rom-plan build/demo/crx-plan.json --frames 45 --chunk-tokens 4700000 --sym-elf build/lr-demo/doomd.elf --out-dir out/runplan
