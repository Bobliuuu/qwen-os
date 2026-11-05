# Live demo: boot QwenOS, type `doom`

An interactive terminal that boots QwenOS, shows a shell prompt, lets you type commands, and runs real DOOM (`/bin/doomd`) when you type `doom` or `run /bin/doomd`.
Everything visible is guest RV32IM code: kernel, shell, DOOM. The host program only forwards your keys, serves disk blocks and paints the framebuffer.

## Tiers: which computer runs the guest

| Mode | Tier | What executes the guest instructions | Speed |
|---|---|---|---|
| `make live-doom` / `tools/qwenos_live.sh` (this page) | **T0, host emulator** (`build/rv32_fast`) | a C RV32IM interpreter on your CPU | seconds to the first frame; `--fps` paces the display |
| `tools/qwenos_live.sh --model` (prints the commands) | **T2, real Qwen model** | the Qwen3.5 checkpoint with the Qwenputer circuit, on a GPU box | about 1.1 k instr/s, a frame is millions of instructions |

The terminal banner says `tier T0` every time it runs. The T0 run is not model evidence: the model-verified parts are listed in the README ("What is real").

## One command

```sh
make live-doom                 # interactive: builds everything, fetches engine + Freedoom on the first run
make live-doom LIVE_ARGS=--auto   # same, but the shell tour and `run /bin/doomd` are typed for you
```

or, once built, `tools/qwenos_live.sh [--auto]`. Needs: `clang` + `ld.lld` with a riscv32 target, `llvm-nm`, `git`, `curl`, `unzip`, `python3`, `cc`.
On macOS: `brew install llvm` (found at `/opt/homebrew/opt/llvm/bin`, override with `LLVM=`), and `ld.lld` on `PATH`.

Inside the terminal: type `help`, `ls`, `cat /README`, `echo hi > /tmp/note`, `cat /tmp/note`, then `doom`.
In the game: arrows or w/a/s/d move/turn, `f` or space fires, `e` uses. `Ctrl-]` (or `Ctrl-C`) quits (handled by the host, never sent to the guest).
Options: `--fps N` (display pacing, 0 = as fast as possible), `--keys file` (extra key schedule), `--disk`, `--wad`, `--elf`.

## Fetching and patching the engine (reproducible)

`make live-doom` runs `tools/fetch_engine.sh` when `.deps/engine/DMC100-Doom/build/sw/nor/E1.img` is missing. Run it by hand with `make engine`. Steps it performs, all inside the repo (`.deps/` is git-ignored):

1. `git clone https://github.com/ArturBieniek4/DMC100-Doom .deps/engine/DMC100-Doom`, `git checkout 0cdc78e`, `patch -p1 < engine-patches/dmc100-qwenos-merged.patch`.
2. Download Freedoom 0.13.0 (`freedoom-0.13.0.zip` from the GitHub release) and unzip `freedoom1.wad` to `.deps/wads/`. Use your own with `WAD=/path/freedoom1.wad`.
3. `make BUILD=build/sw IWAD=... gen` in the engine tree (converter; `tools/nm_noprefix.sh` strips the macOS `_` symbol prefix via `NM`).
4. Link a mode-3 `doomd` once without the data bake to read its RAM layout (`ports/doomdmc/mklayout.py`, `QFLAT_SLOTS=0`), then pack the E1 episode against that layout (`ports/doomdmc/mkimage.sh`) into the NOR disk image `E1.img` (3.9 MB).

The image must be packed against the layout of the same `doomd` build. A mismatch makes doomd panic right after `DOOMD_LEVEL_START` with `plan A: caches end N B into the arena`.
Other locations: `ENGINE_ROOT=dir tools/fetch_engine.sh`, then `DMC=dir/DMC100-Doom` for the build scripts.
No game data is committed; Freedoom is BSD, the engine port is GPL-2.0 (see `NOTICE`).

## Expected output

Banner (stderr), then the guest console, then the game screen (alternate screen, 24-bit colour, status line `guest instr N | frame F | fps`).
`tools/live_transcript.py [frames]` plays the human in a pseudo-terminal and prints this transcript, decoding the game screen into ASCII (a space is darkest, `@` brightest; the kernel framebuffer is 32 x 24 cells):

```
=== QwenOS live | tier T0: guest RV32IM on the HOST EMULATOR (build/rv32_fast), not the model ===
 host = keyboard + disk blocks + display only; shell, kernel and DOOM run as guest instructions
 type: help, ls, cat /README, ... then  doom  (= run /bin/doomd).  Quit: Ctrl-]   (T2 real model: tools/qwenos_live.sh --model)
$ help
ls cat echo [> f] run /bin/X doom exit
$ ls
/README
/bin/sh
/bin/paint
/bin/raycast
/bin/asset
/bin/doom
/bin/doomd
/tmp/note
/tmp/log
$ cat /README
QwenOS: RV32IM kernel, ROM apps, RAMFS, framebuffer, ABI version 1.
$ echo hello qwenos > /tmp/note
$ cat /tmp/note
hello qwenos
$ run /bin/doomd
doomd: DMC100-Doom on QwenOS
doomd: img_init -> 0
doomd: image bytes 3890048
doomd: engine init done
doomd: R_Init/P_Init done
DOOMD_LEVEL_START e1m1

--- DOOM frame 0 (64 x 24 ASCII, decoded from the display ANSI) ---
................................................................
................................................................
........  ......................................................
....................................................  ..........
................        --....----....==--  ....  ..    ........
............::..........    ::..    ::::  ........    ..........
............  ::....::..::::::::::::::      ..::..  ..  ........
........::..  ::      ..............      ....::..  ..--::......
........  ....::      ..                    ..::....        ....
........  ..  ::      ..  ..::..      ..  ::..::              ..
........  ..  ::      ..  ..  ..          ::..::..        ......
........  ..  ::      ..                    ..::          ......
..............::..............................::..    ......  ..
..........::::::::::::::::--::..--::::::::::::::::::::  ........
....                          ::                              ..
....                                                          ..
                                                                
                                                                
                                                                
                                                                
                                                                
..::  ..--......::::::::++::..    ==::......::  ::..--..........
::::..  ++  ::::..  --::++::..**--**..::..    ..::++--::@@..::..
::==..++--==..--......--..==..::..--::--..++::::........@@::....
status line at end: guest instr 4383693 | frame 2
QwenOS live: quit key after 4390912 guest instructions, 2 frames shown (2 frame markers), guest exit code -3
```

Cold boot to the first E1M1 frame is about 4.4 M guest instructions on this typed flow (a few seconds on the emulator). The picture is the E1M1 start view at the kernel's 32 x 24 resolution; the full 320 x 240 frames come from `tools/os_demo.sh`.

## Real model path (T2, needs a GPU box, not run here)

```sh
CHUNKROM=1 make demo-live        # build/demo/qwenos-live-e1m1.elf: typed flow image, chunk ROM, zero disk requests inside doomd
# on a CUDA box with the merged Qwen3.5 checkpoint and qwenputer on PYTHONPATH:
PYTHONPATH=<qwenputer>/experimental/riscv python3 tools/model_doom_qwen.py MODEL_DIR \
    --elf build/demo/qwenos-live-e1m1.elf --kernel-elf build/kernel-live.elf \
    --disk .deps/engine/DMC100-Doom/build/sw/nor/E1.img --target game-frame --keys 'r@1,...' --result-json run.json
tools/model_doom_qwen.py --dry-run   # same plan on the reference machine, no GPU
```

Honest limits of the model path: the model driver runs in segments between frame markers and disk requests, and typed keys can only land on segment boundaries (`--keys 'CHAR@MARKERS'`); it has not been updated to the live key-ring protocol, and the typed `run /bin/doomd` flow has not been model-verified (README, "What is real"). Cost: about 1.35 chip tokens per instruction, millions of instructions per frame, so budget GPU hours and confirm cost before launching.
`tools/qwenos_live.sh --model` prints this and exits.

## Tests

```sh
python3 -m unittest tests.test_live tests.test_shell_live -v   # pty-driven: types into a terminal, reads what it shows
make check                                                      # everything (needs build/ outputs; WAD-dependent tests skip without the engine)
```

`tests/test_live.py::LiveTranscript` runs the whole `--auto` flow and checks the shell lines, `DOOMD_LEVEL_START e1m1` and that the decoded frames are a real picture. `test_shell_live.py::test_help_and_doom_alias` covers `help` and `doom`.

## Known limits

* The display is the 32 x 24 kernel framebuffer, not the 320 x 240 game screen (that needs the 78 kB serial dump per frame).
* T0 speed depends on your CPU; with `--fps 35` the display paces to 35 fps only when the emulator can keep up.
* Walking in the game from the live terminal was exercised by tests with scheduled keys, not by hand in this write-up.

## Screen-recording video

`docs/assets/qwenos-live-boot.mp4` (1280x720, 20 fps, about 67 s) and `qwenos-live-boot.gif` (800 px, 10 fps) are built from these segments, in order:

1. Intro card (4.5 s): tier T0, not the model.
2. Explainer cards "What this is" and "What you are watching" (7 s each): Qwenputer compiles RV32IM into the weights of Qwen3.5-4B, RAM is Gated DeltaNet state, about 1.4 tokens per guest instruction; T0 is the host emulator, T1/T2 are upstream's reference CPU and the real model, identical on everything tested.
3. Real captured terminal: boot, typed shell tour (`help`, `ls`, `cat /README`, `echo > /tmp/note`, `cat`), typed `run /bin/doomd`, then the DOOM frames with the instruction counter panel.
4. Explainer cards "What the model actually did" (8 s), "How slow" (8 s), "Honest bits" (7 s): the verified typed flow (3 A100 chunks, 3,335,072 instructions, 26 segments, zero divergence), the 45-frame, 35-chunk clip, model-emitted pixel bytes (count of byte-exact frames: in progress, taken from `out/clip_modelpixels/STATUS.md`), about 8 to 10 minutes of A100 per frame now (about 18 before the speed-ups, 2.14x per chip token measured, about 8,000x off real time, footnote about 28 minutes by whole-clip division), and what the host does and does not do.
5. Closing card (4 s).

Reproduce:

```sh
python3 -m venv /tmp/v && /tmp/v/bin/pip install pyte pillow     # outside the repo
PATH=/opt/homebrew/opt/llvm/bin:$PATH make live-doom LIVE_ARGS=--help   # build once
INSET_DIR=<dir with frame_01.png.. 320x240 clip frames> /tmp/v/bin/python tools/record_live_video.py all
```

`tools/record_live_video.py capture` types into `tools/qwenos_live.sh` in a pty (70 ms per key) and saves the timestamped byte stream; `render` replays it through `pyte` + Pillow and encodes with ffmpeg.
What is honest in it:

* Tier T0 (guest RV32IM on the host emulator `rv32_fast`) is in the title bar of every frame and on the intro and closing cards. The Qwen model ran none of it.
* Terminal text and the 32 x 24 game picture are the real captured output. Idle gaps are capped at 0.9 s, and the DOOM frames are shown at about 1 s each: the emulator produced all 14 frames in 0.2 s (about 15 ms per frame, 1.8 M instructions each), so the slowdown (about 60x) is stated on screen.
* The 320 x 240 inset is NOT from this session. It is from the separate scripted clip run (`CLIP_LEDGER.md` frames, walking), so it moves while the terminal picture (no keys pressed) stays still. It is labeled as such.
* Explainer cards: model-side numbers (about 8 to 10 minutes of A100 per displayed frame now, a projection from measured chunk speeds; about 18 minutes before the speed-ups; about 28 if the whole clip's chunk wall time is divided by 45, which includes slow early chunks, cold boot and mixed GPUs) are stated as such. The DOOM panel caption uses the same projection. The cards are text only; the model did not produce any frame in this recording.
