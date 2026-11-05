# Non-render (game logic and runtime) instruction reductions, branch perf/sim

All numbers are **host emulator** instruction counts (`tools/rv32_fast`, E1M1 scripted demo, FULL preset 160x200, 15 of 35 tics drawn,
350 game tics, host-served disk = dry run of `tools/mkdemo.sh`). Not a Qwen run, no GPU, no paid service.
Base is `origin/perf/compiler` (164,509,698 instr, 238,221,788 chip tokens). fps and resolution untouched.
Every kept change leaves the console md5 (`1b7e1798...`) and the 151 frame hashes (`2098581f...`) identical and `tools/doomd_regress.sh` PASS
(state and frame hashes equal to `tests/golden`).

## Result

| step | change | steps | delta vs perf/compiler | tokens | delta tokens |
|---|---|---|---|---|---|
| 0 | perf/compiler (tuned LTO + Zba) | 164,509,698 | 0 | 238,221,788 | 0 |
| 1 | unrolled strong `memcpy`/`memmove`/`memset` (`ports/doomdmc/rtlib.c`, `CF_rtlib` in build.sh) | 163,190,963 | -0.80% | 236,545,276 | -0.70% |
| 2 | exact `FixedDiv` fast path for divisors < 2^16 (`ports/doomdmc/fastfix.c`) | 162,660,912 | **-1.12% cumulative** | 235,760,253 | **-1.03% cumulative** |

Text 206,396 -> 208,896 B (ROM headroom now ~16.4 KB), rodata and bss unchanged.

## What was learned about the "sim-only tic"

* A tic without drawing costs about 16k to 37k instructions in the tic list (`TICLIST=1`), not 138k. The 138k to 147k figure is the median over *all* 349 tics (drawn
  tics cost 1.1M to 2.2M). The 129 sim-only tics together cost 4.7M = 2.9% of the run; all game logic (P_*, thinkers, sight, blockmap) is about 10M = 6% including
  the logic that runs inside drawn tics.
* In sim-only tics 41% of the instructions are the NOR/record cache (`rec_get` 17%, `rc_fill` 11%, `nor_read` 10%, `rec_get_miss` 4%): the engine reads map data
  through it. Those belong to the render/hotloops work (rec_get, rc_fill) or to the disk path. `P_Ticker` is 480k (3.7k/tic, an ~8 instr thinker loop over ~104 thinkers).
* Boot and level load are small: boot to level start 192k, load to first frame 2.57M, and that 2.57M is mostly the first rendered frame (R_DrawStrip, V_DrawPatchCols,
  rec_get). `P_SetupLevel` is 31k, `fat_open` 45k.
* The trig decoders are about 4.5M (2.7%): `dmc_tantoangle` 1.87M (55k calls x 34), `dmc_finesine` 1.65M (39k x 42), `dmc_viewangletox` 1.0M (24k x 41).
  They are compressed-table decoders (the engine is built for a tiny ROM); full tables do not fit: rodata is 30.5 of 32 KB before the chunk-ROM window.

## Not kept (measured, no gain or not worth the ROM)

| try | steps vs step 2 | note |
|---|---|---|
| table-driven leading-zero count in `divlu` (packed 2-bit nibble table) | +9k (worse) | clang's branchless seqz chain was already cheaper |
| extra -O3 objects `chains p_maputl p_map p_mobj p_tick` | -175k (-0.11%) | +4.4 KB text; not adopted (ROM is shared with the hotloops branch) |
| extra -O3 objects `rec extents pages level movers lights` | ~0 | |
| extra -O3 objects `st_stuff st_lib hu_stuff hu_lib rtlib` | -107k (-0.07%) | +0.7 KB text; could be adopted later |
| `O_ViewThing` (2.9M, 5.8k calls x 496), `P_CrossSubsector`/`P_CheckSight` | not touched | object-store and sight code, no cheap behavior-preserving rewrite found |
| `dmc_tantoangle` in 32-bit arithmetic (exact: a_lo*j + c*k fits int32) | not done | saves only ~4 instr/call (~0.2M), needs an engine patch or `--wrap`; below 0.15% |
| chunk-ROM verification run of `tools/mkdemo.sh` | exit 99 `DOOM.DAT not usable` | pre-existing in this environment (see COMPILER_BENCH.md); the production `crx_read` path is therefore not measured, only the host-served mailbox path |

## Top remaining non-render hot spots (profile of step 2, whole run)

`nor_read` 6.9M (4.2%, mailbox protocol dominates in this host-served bench), `nor_hw` 3.1M, `nor_col_start` 2.2M, `pump_submit` 1.3M (qlcd, hotloops),
`O_ViewThing` 2.9M, `R_PointToAngle` 2.6M, `FixedDiv` ~1.8M (20.8k of 31k calls have a divisor >= 2^16 and still use `divlu`, 74 instr),
`R_Subsector` 2.2M, `P_CrossSubsector` 1.85M, trig decoders 4.5M, `P_GetSide` 1.3M, `P_Ticker` 1.3M, `P_CheckSight` 1.1M, `Chain` 0.9M, `P_SegSide` 0.9M,
`doomd_main` 2.7M (inlined HUD/band/dirty-column scan, about 435k of it a per-frame 320-bit scan).

## Reproduce

The engine tree must have `engine-patches/dmc100-qwenos-merged.patch` applied (`DMC=<that tree>`). Nothing in this branch changes the engine tree.

```sh
make build/kernel-doomd.elf build/shell.elf build/paint.elf build/raycast.elf build/asset.elf build/doom.elf
DMC=<tree> tools/compiler_bench.sh base      # step 0 numbers (on perf/compiler)
DMC=<tree> tools/simbench.sh sim             # this branch: steps, tokens, md5, "HASH OK" against the baseline md5s
DMC=<tree> tools/doomd_regress.sh            # goldens
# profile only the sim-only tics (PROFMASK is new in tools/rv32_fast.c)
TICLIST=1 build/rv32_fast build/lr-bench-sim.elf $DMC/build/sw/nor/E1.img 154 15c out.bin 4000000000 2>&1 | grep '^tic ' > tics.txt
awk '$6<60000 && $2>=25{print $2}' tics.txt > simtics.txt
PROFMASK=simtics.txt PROF=1 PTOP=45 SYMELF=build/lr-bench-sim/doomd.elf build/rv32_fast build/lr-bench-sim.elf $DMC/build/sw/nor/E1.img 154 15c out.bin 4000000000
```

`FixedDiv` fast-path check: 4e8 random (ua, ub < 2^16) pairs equal `((uint64_t)ua << 16) / ub`.
