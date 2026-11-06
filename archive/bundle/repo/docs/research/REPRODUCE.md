# Reproduce

Legend: [V] = command appears verbatim in a repo file or log that this pass read; [U] = assembled from docs/scripts, not run in this pass.
Nothing here was executed by the author of this record; all [V] marks mean "documented in the source", not "re-run today".
The main repo at `/Users/jhome/qwenos-work/bundle/repo` is the v0.12 baseline: its `tools/rv32_fast.c` is the small original (no `-s`, `-F`, `-W`, `-L`, `REQLOG`, `PROF`); the full emulator options exist only in the patched trees (perf, ram, full, os, test, chunkrom patches). Mailbox addresses passed to `rv32_fast` change with the RAM layout: `100 108` (v1), `3c 44` (ram.patch), `54 5c` (merge tree, `wt-merge/tics.sh`). Read them with `readelf` from `kernel-doomd.elf` symbols `qos_input_mailbox`, `qos_disk_mailbox`.

## 1. Build and regression (baseline repo) [V]
```sh
cd /Users/jhome/qwenos-work/bundle/repo
make clean && make check          # Clang/LLD + readelf + Python 3; 29-35 tests depending on patches
make doom-frame
python3 tools/interactive_frames.py --keys wd
python3 tools/wad_device.py build/qwenos.elf [--wad file.wad]
```
Freedoom: set `QOS_FREEDOOM_WAD=/Users/jhome/qwenos-work/wads/freedoom1.wad` for the viewer tests (md5 b93be13d05148dd01614bc205a03648e).

## 2. Applying the patches [U]
Each patch carries different path prefixes. Apply onto a copy, never the main repo, and expect rejects when stacking (os.patch onto the perf-updated tree failed 1/3 hunks of `qlcd.c`, 1/1 of `qplat.c`, 4/6 of `rv32_fast.c`; see TRACES/merge/os-apply.log).
```sh
cp -R /Users/jhome/qwenos-work/bundle/repo /path/to/work/repo
cd /path/to/work/repo && patch -p1 < docs/research/TRACES/patches/ram.patch          # [V] note says: cd repo && patch -p1 < patches/ram.patch
cd repo2 && patch -p2 < test.patch                                                  # [V] test.notes.txt (apply inside repo2)
# perf.patch / bake.patch use pb/ prefixes over two trees (pb/engine, pb/repo); full.patch and full-engine.patch use absolute
# /Users/jhome/qwenos-work/wt-full/ and wt-engine/ paths: use `patch -p<N>` with N chosen to strip to the tree root [U]
```
The authoritative applied trees are the worktrees `wt-perf/repo2`, `wt-ram`, `wt-full`, `wt-os/repo2`, `wt-test/repo2`, `wt-render/repo2`, `wt-sys/repo2`, `wt-lowres/repo2`, `wt-bake/repo*`, `wt-chunkrom/repo`, `wt-merge/repo` (merge in progress).

## 3. DOOM engine build, emulator run, frames [V from ports/doomdmc/README.txt]
Needs a DMC100-Doom checkout (`DMC=.../engine/DMC100-Doom`) and `make gen/nor-images` there; NOR image `E1.img` (DMC100 `tests/host/mknor.py`, E1 pack).
```sh
make build/qwenos-doomdmc.elf                           # mode 0 attract loop
ports/doomdmc/mkmode.sh 2 [FRAMES [DUMP]]               # mode 1 DEMO1, 2 E1M1 scripted, 3 (os.patch) E1M1 keys only
tools/rv32_fast build/qwenos-doomdmc.elf E1.img 100 108 out.bin MAXINSTR [p@FRAME ...]
python3 tools/doomd_frames.py out.bin freedoom1.wad prefix          # PNGs from a 'p' dump
make doomdmc-image DMCWORK=<writable DMC100 copy>       # ram.patch only: repacks E1 pack + image for the RAM layout
```
Console markers: `DOOMD_LEVEL_START`, `DOOMD_FRAME n tic t`, `DOOMD_FRAMES_DONE`, `DOOMD_DEMO_DONE`.

## 4. Regression and goldens (test.patch) [V from golden README]
```sh
tools/doomd_regress.sh            # compare with tests/golden
tools/doomd_regress.sh --update   # regenerate
python3 tools/doomd_trace_cmp.py ...   # field by field against the host oracle (args [U])
DOOMD_ELF=build/regress/prod1.elf python3 -m unittest tests.test_doomd_regress   # [U]
```
Expected on the unmerged test tree: all identical. On `wt-merge` today: `m1-states` fails from tic 57 (TRACES/merge/regress1.log).

## 5. Emulator gameplay video [V from video README]
```sh
FRAMELOG=1 build/rv32_fast build/qwenos-doomdmc-m2.elf E1.img 100 108 out.bin 40000000000 -s e1m1_route.keys -F 1060
tools/doomd_video.py out.bin freedoom1.wad out.mp4      # only in /Users/jhome/qwenos-work/wt-video
```
ELF built with `ports/doomdmc/mkmode.sh 2` and `XCF="-DQ_DUMP_ALL -DQ_KEYSONLY"`. Expected: 5,457,271,471 instr, frame 0 at 9,058,901.

## 6. Low-res / frame-skip sweeps [V from TRACES/lowres scripts]
```sh
cd repo2 && ports/doomdmc/lowres.sh NAME "-DQ_DUMP_COMPACT -DQ_RN=15 -DQ_RD=35" [dump]
./lr_run.sh NAME [maxinstr]       # prints TICS / DISK / GAMETICS / LEVEL / steps (scripts hardcode /Users/jhome/qwenos-work/wt-lowres)
```

## 7. Upstream reference CPU (T1) [V from README]
```sh
PYTHONPATH=/Users/jhome/qwenos-work/qwenputer/experimental/riscv python3 tools/upstream_ref.py build/qwenos.elf --wad-device
PYTHONPATH=... python3 tools/upstream_probe.py build/qwenos-model-probe.elf
PYTHONPATH=... python3 tools/upstream_doomd.py ...            # doomd vs C twin [U arguments]
```
Expected: exit 0, `QWENOS_BOOT_OK`, 120,267 instr.

## 8. Real model (T2) [V from docstrings; needs GPU, confirm cost first]
```sh
# host-only plan / dry run (reference machine stands in for the model)
PYTHONPATH=<qwenputer>/experimental/riscv python3 tools/model_doom_qwen.py --elf build/qwenos-doomdmc.elf --disk E1.img --dry-run
# model probe
python3 tools/model_probe_qwen.py /path/to/Qwen3.5-4B-Qwenputer --elf build/qwenos-model-probe.elf
# boot-frame (this is what produced TRACES/model/boot.json): ~24 min on an A100, 1,552,382 instr
python3 tools/model_doom_qwen.py MODEL_DIR --elf build/qwenos-doomdmc.elf --disk E1.img --target boot-frame --result-json boot.json
# chunked runs across GPUs
python3 tools/model_doom_chunks.py plan --n 4 --out-dir D <model_doom_qwen.py args>
python3 tools/model_doom_chunks.py merge --out-dir D
# chunk ROM: python3 tools/chunkrom.py REQLOG DISK --greedy [--budget B] --out plan.bin   ; model run adds --rom-plan JSON
```
Marker numbers shift with every engine rebuild: re-read them with `rv32_fast ... "frame K at"` and pass `--snapshot-marker`. The exact model host command used for boot.json (flags, checkpoint path) is not in the files; checkpoint path `~/q4-rv1` on the fleet boxes. A100 host IP and key are not recorded here.

## 9. Live demo (os.patch) [V from patch README]
```sh
make live
OS=live ports/doomdmc/mkmode.sh 3
tools/qwenos_live.sh            # type: run /bin/doomd <Enter>; --auto types it; --fps N; quit with Ctrl-]
tools/os_demo.sh                # scripted boot -> typed command -> E1M1 -> PNGs and instruction counts
```

## 10. Full-game checks [U arguments]
`tools/doomd_full_test.py`, `tools/doomd_episode_test.py`, `tools/doomd_play.py`, `tools/mkdisk.py` (full.patch); `rv32_fast -s SCRIPT -F maxframes -W disk-out`. Key scripts are in TRACES/full/*.keys. Results: TRACES/full/results.txt.
