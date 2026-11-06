# 09 Instruction optimization (perf.patch)

Goal: cut guest instructions per game tic and disk requests per tic, bit-exactly (frames identical to the original build).

Method: added a profiler to `tools/rv32_fast.c` (`PROF=1 PHASES=f1,f2,..` self-instruction count per symbol per phase; `TICSYM` per-tic deltas; `REQLOG`). Profile showed (TRACES/perf/profile_phase2_prof2.txt, 91.6 M instr phase): R_SolidColumn 11.1 %, sys_entry 10.1 %, R_ReplayWall 9.2 %, rec_get 6.8 %, rec_get_slow 6.1 %, rc_fill 5.7 %. Changes: LRU table lookup instead of a shift loop, hit-lookup leaf function, cached translation runs per DOOM.DAT part (`img.c`, `extents.c`), inline DISK_READ (request + bounded wait + copy in one call), virtual-clock jump to the next tic, console fast path (PUTC), baked map-stream stub (`qbake.c`, `bakemap_stub.c`).

Numbers (agent report): mean instructions per tic 10.47 M -> 3.52 M; disk requests 6,807 -> 2,195. Baseline file `v0long.log` (TRACES/perf/v0long_baseline_frames.log.gz): per-frame deltas of 4.8-6.9 M instr over about 2,000 frames (826 unique consecutive frames of 1,658 compared), consistent with 10.47 M per tic if each tic held two draws (the redraw skip, experiment 08, removes the second).
Verification: `verify.sh NAME` rebuilds, hashes frames (`fh.py`) and requires IDENTICAL against `base/v0.h`; `cmp.py` for the long run (alignment then compare).
Metric warning: later tools report per-tic cost as `GAMETICS` (instructions between G_Ticker entries) which is much smaller (about 1.3 M mean in TRACES/lowres, 3.09 M in the merged regress for DEMO1). The 10.47 M/3.52 M pair uses the older per-tic definition and a different tic mix; do not compare it with GAMETICS numbers.
Result: worked. Files: `engine/port/data/{cache,extents,img}.c`, `port/game/i_dmc.c`, `ports/doomdmc/{qplat,qlcd,doomd_main,qbake,bakemap_stub,build.sh}`, `kernel/main.c`, `include/qos.h`, `tools/{rv32_fast.c,bake_map.py,fh.py}`.
Patch: TRACES/patches/perf.patch (md5 67c30a734bb4ca2982ba509ec2e6b36d; paths prefixed `pb/engine` and `pb/repo`).
Reproduce: not re-run; see REPRODUCE.md "optimization verification" (unverified).
