# How QwenOS runs DOOM (the picture book)

Look, don't read. Every picture moves. For the headline numbers see the [README](../README.md); for the evidence see [research](research/README.md).

<p align="center"><img src="assets/hero-terminal.svg" alt="A terminal boots QwenOS, shows the dollar prompt and types run /bin/doomd" width="100%"><br><img src="assets/qwenos-doom-3s.gif" alt="3-second E1M1 clip: 45 frames, all verified through the Qwen model" width="480"></p>

*Real E1M1 frames from the emulator (the C emulator renders the pixels; see the honesty box below).*

## 1. The stack

A keystroke dives six layers down. A frame climbs back up.

<p align="center"><img src="assets/stack.svg" alt="Animated stack: you, shell, /bin/doomd, DMC100 engine, kernel syscalls, Qwenputer circuit inside Qwen3.5" width="100%"></p>

The host is a very dumb helper: it pushes key bytes and serves disk blocks. It never runs game logic.

## 2. One frame, token by token

About 0.49 M instructions per game tic, 1.345 chip tokens each.

<p align="center"><img src="assets/one-frame.svg" alt="Instruction chips turn into token blocks, counters tick up, a frame pops out with marker 0x02" width="100%"></p>

Boot to the `$ ` prompt is 184 instructions (186 in the merged build). Typing `run /bin/doomd` costs about 1,050.

## 3. The 32 KiB map

doomd **takes over** nearly all the RAM. The code lives in read-only ROM, because this CPU cannot execute from RAM.

<p align="center"><img src="assets/memory-map.svg" alt="RAM map and ROM map, with the chunk window at 0x29000..0x3f000" width="100%"></p>

## 4. Lockstep: every token must match

<p align="center"><img src="assets/lockstep.svg" alt="Three lanes, model, reference CPU and host truth, march in step with checks; a faded mismatch scenario stops the run" width="100%"></p>

<p align="center"><img src="assets/verify-strip.svg" alt="Timeline strip: snapshot, generate, compare, segment ok, next snapshot" width="100%"></p>

What has actually run on the model: a probe, a title frame (6,563 instr), and a cold boot to the first frame marker (1,552,382 instr, 292 segments, zero divergence, earlier pre-merge build). Since then the model has also verified a 45-frame (3 s) scripted E1M1 clip: 35 chunks, 81,065,587 instructions, zero divergence, with pixels rendered by the emulator ([ledger](CLIP_LEDGER.md)).

## 5. Why chunk ROM removes the disk pauses

<p align="center"><img src="assets/chunk-rom.svg" alt="Before, 165,054 disk pauses. After, an 89 KB data-ROM window per chunk and 4 pauses" width="100%"></p>

`tools/chunkrom.py` plans which disk bytes each stretch of the game needs and preloads them into the window at 0x29000..0x3f000. If a read misses, the engine still falls back to the disk mailbox, so correctness never depends on the plan (a deliberate-miss test gives byte-identical output). Price: +10.6 % instructions.

## 6. Chunking across GPUs

<p align="center"><img src="assets/gpu-chunks.svg" alt="The 3-second clip split into chunks, fanned out to GPUs, merged into a ledger" width="100%"></p>

The clip was split into 35 chunks and run on 29 Modal A100, 3 Lambda A100 and 3 AWS A10G jobs, each verified in lockstep. The diagram shows the idea; the real ledger is [CLIP_LEDGER.md](CLIP_LEDGER.md).

## 7. The journey

<p align="center"><img src="assets/journey.svg" alt="Timeline from the v0.11 viewer to real DOOM, upstream CPU, model boot frame, chunk ROM and the clip" width="100%"></p>

## Honesty box

> The pixels in the GIF come from the emulator. The model verifies the instruction trace (frame marker, console bytes, instruction count, lockstep), not the pixels. Disk is host-served, keyboard input is simulated, the clock is virtual, and it is not real time (about 1.1 k instr/s). The 3-second clip (45 frames, 35 chunks) is model-verified for the instruction trace only; the typed `run /bin/doomd` flow is not. Full list: [HONESTY.md](research/HONESTY.md).

## Where to go next

- [MERGE_NOTES.md](../MERGE_NOTES.md): addresses, numbers, known gaps of the final build.
- [docs/research/](research/README.md): TL;DR, status, honesty list, every experiment.
- [HISTORY.md](HISTORY.md): older per-version notes.
