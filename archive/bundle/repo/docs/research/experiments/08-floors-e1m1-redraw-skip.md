# 08 Floors, E1M1 start mode, redraw skip, -O2, fastfix

Goal: first cost reductions and an E1M1 entry point so a model run does not have to sit through title/demo.

Changes (`ports/doomdmc/README.txt`): mode 2 = E1M1 player start with scripted buttons (`q_script`); plan-B textured floors (flat-colour fallback earlier); `-O2` instead of `-Oz`; `fastfix.c` (FixedDiv via divu, bit-exact); `qimg.c` (extent run cache); `qsolid.c` (repeat floor/ceiling columns copied); main loop skips the redraw of a frame that follows no tic, because the virtual clock makes every other `TryRunTics` call tic-less.

Numbers (agent report): first E1M1 frame 6.19 M instr, 5.14 M per tic. The 5.14 M/tic figure also appears as measured in the video run (mean over 1,059 tics, includes the serial dump).

First-frame instruction counts by build (they differ, they are not errors):
| Source | Build | Count |
|---|---|---|
| agent report | first DEMO1 frame, port v1 | 11.26 M |
| agent report | first E1M1 frame, after floors/skip | 6.19 M |
| `model_doom_qwen.py` docstring | game-frame, marker #342, at that build | 5,842,573 |
| out/video README | frame 0 of Q_DUMP_ALL video build | 9,058,901 |
| os.patch README | cold boot -> first E1M1 frame, live mode 3 | 3.73 M (3.92 M before) |
| lowres batches (TRACES/lowres) | `first_game_frame_at` | 3,914,682 (base), 2,961,951 (detail 2) |

Result: worked; later bugs found in `qsolid.c` (experiment 16).
Reproduce: `ports/doomdmc/mkmode.sh 2 [FRAMES [DUMP]]`; `tools/rv32_fast ELF IMG 100 108 out.bin MAXINSTR`.
