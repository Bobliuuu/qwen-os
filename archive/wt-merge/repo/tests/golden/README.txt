Goldens of tools/doomd_regress.sh (regenerate with: tools/doomd_regress.sh --update)

doomd_m1_states.txt   "<gametic> <fnv64>" after every game tic of DEMO1 (mode 1, 260 frames): the DMC100
                      lockstep hash (tests/lockstep/hash.c: globals, player, sectors, every live mobj; rndindex
                      zeroed because M_Random counts frame draws) computed in the guest.
doomd_m1_frames.txt   "<tic> <md5-12>" for every frame whose picture (320x240 canvas + palette) differs from the
                      previous one. DEMO1 frames were verified IDENTICAL to the original pre-optimisation build
                      (base/v0long.h, 256 unique frames incl. unique frame 202) when these were generated.
doomd_m2_*.txt        the same for the E1M1 scripted run (mode 2, 100 frames; q_script in doomd_main.c).
perf_baseline.txt     "<mode> <mean instr per game tic> <disk requests per tic> <game tics>" of the production build.

State hashes are optimisation independent (they changed in none of the builds tried: -Oz/-O2, with and without
qsolid/fastfix/qimg/bake/redraw skip, original engine tree). They are NOT identical to the host oracle's stream
tic for tic: the guest's object store lists mobjs in a different order (tier order, not spawn order) from tic 71
of DEMO1 on, and hashes target ordinals; compare single tics field by field with tools/doomd_trace_cmp.py.
