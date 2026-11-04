# 17 Bake: hot disk data cut into the data ROM (bake.patch)

Goal: remove disk requests (each is a model pause costing about 1.7 s) by baking the E1M1 hot set into the 120 KiB data ROM.

Method: `tools/bake_route.sh` runs unbaked E1M1 walks (routes `Q_ROUTE` 1, 2, >=10 pseudo-random) with `REQLOG`; `tools/bake_select.py` picks 4-byte-unit block lists to fill the ROM budget (BUDGET 91,700); `tools/bake_map.py` cuts them out of the NOR image into `bakemap.c`; `qbake.c` serves reads from ROM (record-cache fills, `img_read`, direct column read) and is enabled only if the image header CRC matches. `ports/doomdmc/bake_e1m1.txt` = 21,164 units in 844 runs from 7 request logs. `tools/bake_eval.py` scores on other logs; `tools/bake_reqan.py` analysis. `NOBAKE=1` builds without.
Numbers (agent report): about 95 % fewer disk requests on the walks it was tuned for. Hold-out routes are what `bake_eval.py` measures; the 95 % is for E1M1 and does not generalize to other maps (the hot set is E1M1-specific, E1M6 bake dropped in chunk-ROM build).
Result: worked for E1M1, then shelved in favour of chunk ROM (experiment 18). Reasoning below is our reading of the design, not a recorded decision: a bake is fixed for the whole run and bounded by 90 KB, whereas chunk ROM refills the window per chunk and covers any route, and it is generated from the exact requests of the chunk. Bake stays as a build option. Disadvantage: it consumes the data ROM that ram.patch had used for flats (rodata budget "will not fit in region DROM" failure when rodata grows).
Files: `ports/doomdmc/{bake_e1m1.txt,bakemap_stub.c,qbake.c,qimg.c,build.sh,doomd_main.c}`, `tools/bake_*.py`, engine `r_data.c`, `port/data/{cache,fat12}.c`.
Patch: TRACES/patches/bake.patch (md5 a65ce052...).
