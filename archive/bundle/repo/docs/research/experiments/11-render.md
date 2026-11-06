# 11 Renderer work (render.patch)

Goal: reduce renderer instructions (R_SolidColumn, R_ReplayWall, column loops).

Method: new `port/render/r_inner.c` with a hand-scheduled inner loop (assembler using `gp`, `.option norelax`, saved/restored gp), inlining of R_MapPlane/R_MakeSpans into R_DrawPlane, noinline cold paths (`rec_get_full`, `rec_get_miss`), `-mrelax` plus linker `--relax --relax-gp` with `__global_pointer$ = 0xec0` in `frame.ld` (global-pointer-relative addressing replaces lui/addi pairs), `crt0` sets gp. Earlier build rules were `-msmall-data-limit=0` and `--no-relax`, which kept every global access two instructions.
Numbers (agent report): -18 % instructions.
Result: worked. Caveat: linker relaxation changes the ELF layout; the layout checks (`tools/check_layout.py`) and the RAM plan must be re-run after enabling it (build.sh has `RELAXFLAG`/`LDRELAX` switches to turn it off).
Files: `engine/DMC100-Doom/engine/{p_mapdata,r_data,r_plane,r_segs}.[ch]`, `port/data/cache.c`, `port/render/r_inner.c`, `repo2/apps/doomd_crt0.S`, `include/qos.h`, `kernel/main.c`, `ports/doomdmc/{build.sh,frame.ld,qlcd.c}`.
Patch: TRACES/patches/render.patch (md5 8a23f20b0ccf09f3c18fd9b5e66a4036). Frame equivalence was checked with `chk.sh`/`cmp.py` in the work tree (logs not retained).
