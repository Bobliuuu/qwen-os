# MERGE_NOTES: one E1M1-focused QwenOS DOOM build

Tree: `<repo root>` (engine copy: `../engine/DMC100-Doom`, the base engine was copied, never modified in place).
Nothing is committed. Scope: E1M1 only (no bosses/episodes/sound/saves). Target: fewest instructions and fewest disk
pauses per tic for 5-10 s of E1M1 run through the model.

## Commands

| what | command |
|---|---|
| model-run image (mode 2 scripted E1M1, FULL preset = draw 15 of every 35 tics, chunk ROM) | `make demo-elf`  -> `build/demo/qwenos-e1m1.elf`, `crx-plan.bin`, `crx-plan.json`, `reqlog.bin` (also dry run + CRX verification run) |
| same, no chunk ROM (host serves disk) | `CHUNKROM=0 tools/mkdemo.sh full` |
| other presets | `make demo-elf PRESET=balanced` / `max` / `none` (none = draw every tic) |
| typed flow (boot -> prompt -> `run /bin/doomd` -> E1M1 mode 3, keys only) | `CHUNKROM=1 make demo-live` -> `build/demo/qwenos-live-e1m1.elf`, `live-crx-plan.{bin,json}`; scripted replay `tools/os_demo.sh`; interactive terminal `tools/qwenos_live.sh` |
| tests | `make check` (kernel, layout, Python ref, 65 unit tests), `tools/doomd_regress.sh` (state/frame goldens), upstream lockstep: `PYTHONPATH=<qwenputer>/experimental/riscv DOOMD_ELF=build/demo/qwenos-e1m1.elf LOCKSTEP_INSTR=6000000 python3 -m unittest tests.test_doomd_regress` |

Env knobs of `ports/doomdmc/build.sh`: `FLATS=off|map|all|none` (default off), `NOBAKE=1`, `BAKE_MAP=n`, `RELAXFLAG`/`LDRELAX`,
`QHASH/QTRACE/NOSOLID/NOFASTFIX/NOQIMG` (test.patch). `DMC` defaults to `<repo>/../engine/DMC100-Doom`.

## FINAL ADDRESSES (from the kernel ELF, `readelf -sW build/kernel-live.elf` / `kernel-doomd.elf`; both identical)

| symbol | address | notes |
|---|---|---|
| null guard | 0x000-0x0ff | stays zero forever, see "ROOT CAUSE" below |
| takeover stack (`__tstack_top`) | 0x100-0x13f | 64 B; the normal kernel stack is `qos_kstack` in the overlay |
| `qos_kv` (kernel state, first word = key read count) | 0x140 | `QOS_KEY_RD`; doomd resumes its own ring reader from it |
| `qos_input_mailbox` | **0x154** | `{u32 seq; u8 q[4]}` key ring |
| `qos_disk_mailbox` | **0x15c** | request_seq, offset, length, ready_seq, status, then 256 B window at 0x170 |
| `qos_framebuffer` | **0x270** | 32x24, 768 B, resident, doomd writes it directly (`Q_FB`) |
| `__core_end` = `QOS_DOOMD_RAM_BASE` | 0x570 | doomd owns 0x570..0x8000 (30,800 B), stack top 0x8000 |
| `qos_key_park` | **0x40044** | single `ret` in kernel ROM (same pc in kernel-doomd.elf and kernel-live.elf); recompute with `readelf -sW` after any kernel change |
| chunk ROM window (`Q_CRX_BASE`) | **0x29000**..0x3f000 | NOT 0x28c00: the merged rodata is ~800 B bigger, the base moved up 1 KB; `crx-plan.json` carries `base` |

Key push protocol (what a pause/resume driver must do), kernel-side read counter lives at 0x140:
1. stop when pc == `qos_key_park` (or at a frame/segment boundary), 2. `seq = u32[0x154]`, 3. write byte K to `0x158 + (seq & 3)`,
4. write `u32[0x154] = seq + 1` LAST. Never more than 4 keys between guest polls. rv32_fast args are `<kbox> <dbox>` = `154 15c`
(hex); `-W <park pc hex> -K <schedule>`; frame-buffer log `FBADDR=270 FBLOG=file`.

**Model chunk driver (tools/model_doom_qwen.py, owned by another agent, NOT touched here):** it reads `qos_input_mailbox` /
`qos_disk_mailbox` from the kernel ELF symbols, so the new addresses need no change, BUT (a) its key injection must use the ring
protocol above (the stock bundle version writes a 32-bit key at +4 and `seq = 100+n`, `self.kseq = 100`: wrong for the ring), (b) it
must read the chunk window base from `crx-plan.json` (0x29000), (c) the docstring still says `100 108`. One merge-time test,
`tests/test_model_doom_plan.py::test_key_inside_a_segment_is_refused`, is marked **expectedFailure** because it needs the updated driver.

## Patches applied (order) and what was kept

1. **perf.patch**: all of it (kernel word copy, DISK_READ syscall 21, profiler, cache/extents/img, bake_map; E1M6 default bake changed to E1M1 and then OFF by default, see decisions).
2. **sys.patch**: inline disk read in `nor_chunk`, direct fb writes (`fb_col`/`adv`), direct key mailbox, direct `q_putc` ecall; fixed core addresses (re-homed, see below).
3. **keyboard fix** from full.patch: `dji_tic` always calls `pad_set` (pad always present). Nothing else of full.patch (no episodes, no savegame/DISK_WRITE, no extra converter changes, no extra debug keys). The rv32_fast key harness (`-F`, scripted keys) comes from os.patch's `-K`; `tools/doomd_play.py` was taken from full.patch and rewritten to emit `-K` schedules (keys: w s a d space/f e esc/m enter p only).
4. **render.patch**: engine (p_mapdata, r_data, r_plane, r_segs, cache.c, r_inner) + linker relaxation with gp (`__global_pointer$` re-set to 0xe70 for the new RAM base: window 0x670..0x166f) + word-copy disk path. Its `FB_COL` syscall (22) was DROPPED (clashes with os KEY_WAIT=22, and sys's direct fb stores are cheaper than any syscall).
5. **ram.patch (selected)**: the RAM-saving parts that are compatible: the core is rebuilt as a compact fixed-address core (below), the normal kernel stack moved to the overlay + `qos_resume_enter`, kernel state packed into 20 B, `last_present_checksum` moved to the overlay, `QOS_RAM_BEGIN` back to the 0x100 guard. NOT taken: fb moved out of RAM with FB_COL console packets (would break the live fb view, sys direct writes, os FB_PTR and cost instructions), 64 B disk window (would add ~25k requests/350 tics; 256 B kept), ROM flats (90 KB, see decisions), `-Oz` (build stays `-O2`), cache geometry changes (perf's 32 B x 16 sets x 4 ways kept), always-textured/ARENA_MAX engine hacks (kept in the engine behind `-DQOS_FLATROM`, off).
   ram.patch's base is an older tree (no modes/fastfix/qimg/qsolid), so it was never applied as a patch.
6. **os.patch**: key ring, KEY_WAIT=22 / FB_PTR=23, live shell, mode 3, zero-RAM takeover contract (kernel zeroes RAM from `QOS_DOOMD_RAM_BASE`, doomd no longer memsets; no kernel bss loop), qcrc.c, rv32_fast `-L/-K/-W/-F`, os_demo.sh, qwenos_live.sh, keysched.py.
7. **test.patch**: qsolid.c fix (present: `ports/doomdmc/qsolid.c` keeps the last computed column as <=24 runs), regress harness + goldens (restored to the ORIGINAL goldens, unchanged), QHASH/QTRACE/NOSOLID/... knobs, `REGDUMP`.
8. **lowres.patch**: engine files + `lowres.sh` presets, `Q_RN/Q_RD` frame skip, PUMP_QUAD/ROW2, `Q_DUMP_COMPACT`; qlcd.c `pump_submit` re-merged by hand with sys's direct fb path.
9. **chunkrom.patch**: `crx_read` in `nor_chunk`, `tools/chunkrom.py`, rv32_fast `CRXPLAN/CRXBASE`, `Q_CRX_BASE_LD`, lowres.sh `CHUNKROM=1`.
10. **bake.patch**: not present at merge time; the E1M1 bake is not used with CHUNKROM=1 anyway (window needs the data ROM). Without CHUNKROM, `BAKE_MAP=1 ... build.sh` (old `bake_map.py`, 53 KB of E1M1 streams) is available: `NOBAKE` unset.

## Decisions by judgment

* **Syscall numbers**: perf `DISK_READ=21` kept; `DISK_WRITE`/`FB_COL` (22) dropped; os `KEY_WAIT=22`, `FB_PTR=23`. No DISK_WRITE.
* **ROM flats vs bake (decision b)**, measured on E1M1 mode 2 tics 0-349, the old image, perf+sys base (requests are mailbox requests = model pauses):
  config off (disk flats, E1M6 bake that does not apply): 1,214,857 instr/tic (30-300), 880 req/tic; ROM flats of 88 flats (90 KB, ram.patch): 1,213,283 instr/tic, 877 req/tic (-1.5 % requests, tiny gain: the 4-slot flat cache already serves E1M1); E1M1-only flats (48 flats, 48 KB): same 877; E1M1 bake only (53 KB): 1,168,586 instr/tic, 517 req/tic (-41 % requests). Flats from ROM are therefore not worth the data ROM; the bake was, until **chunkrom** (decision by main) which wants the whole 0x29000..0x3f000 window and removes ALL in-doomd requests. Final: `FLATS=off`, `NOBAKE` when `CHUNKROM=1`. Frames with ROM flats were pixel-identical anyway.
* **Mailbox addresses (decision c)**: ram.patch's 0x3c/0x44 was adopted in spirit (compact core, ring + disk mailbox + fb resident) but the final set is 0x154/0x15c/0x270 because of the null-guard finding below. Accepted by main.
* **Floors**: textured exactly as before (k plan of the unchanged E1.img); no floor/preset change in the default FULL preset beyond skip 15/35. E1.img was not rebuilt (md5 6287a13cc1079b697e1885f8f6327e06).
* Chunk window base 0x29000 instead of 0x28c00 (rodata of the merged doomd = 32,016 B + .data load 92 B does not fit 0x21000..0x28c00).

## ROOT CAUSE found during the merge: the 0x00-0xff null guard is semantic

First merged build failed `tools/doomd_regress.sh` `m1-states` (DEMO1 state hash from tic 57, 139/260 lines differ; frames identical, m2 identical). Bisect with `test.patch` applied to perf+sys, perf+render, perf+sys+render (all pass), then my tree with the old kernel/core files swapped in (passes) => only the kernel RAM layout. RAM base, bake, flats, keyboard fix, qcrc, zero contract, relaxation were all individually excluded. Cause: the engine reads through NULL pointers at small offsets (mobj/player fields). In the old layout bytes 0..0xff were never written (always zero); my first compact core put live data (takeover stack, kernel state) at 0x00..0x6f, so those reads returned stack garbage and the mobj store order at tic 57 differed (same multiset, identical frames). Fix: the core now starts at 0x100 behind a zero null guard (kernel.ld `. = 0x100`, `QOS_RAM_BEGIN=0x100`). With the guard: m1-states AND m2-states AND frames identical to the ORIGINAL goldens, no golden was changed. This costs 256 B of RAM but is required for identical game logic. **Any future core layout must keep 0x00..0xff zero.**

## Conflicts resolved by hand (.rej leftovers; none remain in the tree)

* os.patch: kernel/main.c (2 hunks: input ring struct, takeover run/zero), build.sh (qcrc, 1), doomd_main.c (zero contract, 1), qlcd.c (q_fb store, dropped: sys direct), qplat.c (key drain, rewritten against the ring and the direct mailbox), rv32_fast.c (4 hunks: took wt-os's file, re-applied sys's FBLOG/DISKLAT/SYSPC by hand, tic-line `req` column, FBLOG).
* render.patch: kernel/main.c (takeover whitelist hunk + FB_COL implementation removed), qlcd.c (FB_COL call, dropped).
* test.patch: build.sh (2 hunks), rv32_fast.c (REGDUMP).
* lowres.patch: doomd_main.c (frame-skip hunk), qlcd.c (pump_submit merged with fb_col).
* chunkrom.patch: doomd.ld, qplat.c (crx block + hook in the sys inline `nor_chunk`), rv32_fast.c (3 hunks).
* Also by hand: `build.sh` DMC default (`$REPO/../engine/DMC100-Doom`; os.patch silently reverted it once: always check `grep '^DMC=' ports/doomdmc/build.sh`), `FLATS`/`FLATDEF` knobs, tests/tools symbol rename `framebuffer` -> `qos_framebuffer`, `key_seq_seen` -> `qos_kv`, tests that hardcoded 0x100/0x108, `tools/doomd_regress.sh` DMC default and mailbox args, `chmod +x` of scripts that patch(1) drops.
* `mkmode.sh` always rebuilds objects (`FORCE=1`, it used to copy stale `.o` from build/doomdmc) and accepts `MODE_CF`, `LDX`.

## Results (E1M1 mode 2 scripted, 350 game tics, rv32_fast; instr counts are guest RV32 instructions, chip tokens ~ 1.35 x)

| build | instr/tic first 30 | instr/tic tics 30-300 | first game frame at | total steps (350 tics) | disk requests |
|---|---|---|---|---|---|
| perf+sys baseline (pre-merge, `ps`) draw every tic | 2,608,363 | 1,214,857 | n/a | 461.8 M | 340,890 (880/tic) |
| merged, draw every tic (`lr0`, bake E1M1) | 2,104,739 | 1,038,606 | 2,929,695 | 391.2 M | 201,506 (517/tic) |
| pre-merge FULL preset (wt-lowres ref built from lowres.patch) | n/a | n/a | n/a | 227.1 M | 165,061 |
| **merged FULL (skip 15/35), host serves disk** (`CHUNKROM=0`) | 940,482 | 485,801 | 2,931,397 | **180,549,500** | 165,054 (462/tic) |
| **merged FULL + chunk ROM** (`make demo-elf`) | 1,089,238 | 538,573 | 3,417,725 | **199,742,409** | **4 total, 0 inside doomd** |

(instr/tic is the mean over all game tics in the range, skipped-draw tics included. Merged FULL is -20.5 % vs the pre-merge FULL build; chunk ROM costs +10.6 % instructions here, plus the plan switches at 5 frame-marker counts.)
Typed flow (`tools/os_demo.sh`, mode 3, draw every tic): cold boot -> prompt 186 instr, typing `run /bin/doomd\n` 1,050 (70/key), takeover entry 681, takeover -> doomd_main 1,882, OS total 3,799, cold boot -> first E1M1 frame 2,871,070.

Chunk plan (`tools/chunkrom.py --greedy`, window 0x29000..0x3f000 = 86,016 B max): 5 chunks at frame markers 0-4, 4-17, 17-31, 31-100, 100-152; windows 84,716 / 87,932 / 87,616 / 88,444 / 74,744 B (budget 0x3f000-0x29000 = 90,112 B, all OK). Verification run: `CRX chunk ... reqs` = 2, 0, 0, 0, 0; the 4 total requests are 12-byte reads at offset 0 by the boot-script apps `/bin/doom`/`/bin/asset` (before doomd and after the warm reboot at marker 350), none inside doomd. Typed flow (`CHUNKROM=1 make demo-live`, 150 markers, 15 typed keys + in-game keys): chunks 0-4, 4-19, 19-34, 34-61, 61-150, `reqs=0` in all five.

RAM (doomd): data+bss end 0x16b0 (frame region starts 0x16b0), stack reserve 1,408 B (0x7a80..0x8000), **stack high-water measured**: 960 B on E1M1 350 tics (FULL and FULL+CRX, painted-stack scan of the final RAM dump), 956 B on DEMO1 260 tics => 448-452 B margin. No `plan ... caches end into the arena` panic and no `PANIC` in any run console (E1M1 350 tics x all presets, DEMO1 260 tics).

## Gates and evidence

1. Clean rebuild: `rm -rf build; make demo-elf` twice => identical numbers; md5 `build/demo/qwenos-e1m1.elf` = bca0d1ad41c3f0571b349b588f12a3ee, `crx-plan.bin` = af843bac13f2cbab6eb2409748209c5d, `crx-plan.json` = 75684b5ad0f0efd1c4f4ae88b036e30a, E1.img = 6287a13cc1079b697e1885f8f6327e06 (final build after the null-guard fix; an earlier build before that fix had a different ELF md5 but the same instruction counts and plan md5).
2. `make check` green; `tools/doomd_regress.sh` PASS: m1-states 260 lines and m2-states 100 lines identical to the ORIGINAL goldens, m1-frames 257 / m2-frames 99 identical, production vs check builds same sequence. CHUNKROM=0 vs CHUNKROM=1: 151 frame-buffer hashes and the whole console stream byte-identical (also with a deliberately broken plan, see 5).
3. FULL preset vs pre-merge FULL build (wt-lowres + chunkrom reference rebuilt from lowres.patch): 151 frame hashes identical; the full-resolution serial dump of the first 120 tics (51 frames, `lowres.sh ... dump`) is byte-identical (1,688,867 bytes). qsolid fix present; the DEMO1 260-tic frame goldens (include tic 206, the 8-pixel bug) pass.
4. Three-way lockstep >= 5M instructions: rv32_fast vs Python reference (console bytes, 32 KB RAM, pc, x1..x31 at 1.2M/3M/6M) vs official `chipformer.rv.ref.Machine` (`upstream_doomd.py --compare-fast`, console + final RAM) on the merged `qwenos-e1m1.elf` for 6,000,000 instr (through the level load and 2 frames): all equal. Repeated on `qwenos-e1m1-win0.elf` (same image with chunk 0's window preloaded in the data ROM at 0x29000 = the `fill_drom` effect): all equal. Typed-boot key schedule (`/tmp/lockkeys.py`-style: boot -> `run /bin/doomd\n` typed at `qos_key_park` -> takeover -> level -> keys) on the live m3 ELF, Python reference + `keysched.Driver` vs rv32_fast `-K`, 6M instr: console, RAM, pc and all registers equal (18 key pushes).
5. Deliberate miss: the last extent of every chunk was made unreachable (`off = 0xFFFFFFF0` in the window table): guest falls back to the mailbox (reqs 68/61/52/0/13 per chunk, 1,859 total), 151 frame hashes and console byte-identical to the no-chunk run.
6. Key protocol addresses recomputed from the final kernel ELF (table above); keysched replays identical in Python ref and rv32_fast (gate 4); `tests/test_shell_live.py::test_typed_launch_reaches_e1m1_and_key_is_not_lost_across_takeover` (a key pushed after takeover entry still turns the player) and the ring tests pass.
7. RAM / stack: measured, see above.
8. Costs vs pre-merge: table above.

## Known gaps / not verified

* Python reference and upstream lockstep run 6M instructions (level load + 2 frames), not the whole 350 tics (Python speed); rv32_fast vs itself is covered by the determinism test and the whole-run frame-hash equalities.
* `tests/test_model_doom_plan.py::test_key_inside_a_segment_is_refused` is expectedFailure until the model driver is updated.
* bake.patch (wt-bake) was not available; with CHUNKROM=1 the data ROM is the chunk window, so no bake.
* chunk ROM adds +10.6 % instructions in this build (chunkrom note says ~6.6 %, guide-table follow-up ~3 %): the window lookup is in `crx_read` in qplat.c.
