# Typed flow on the real Qwen model

Goal: run the typed flow (cold boot, shell prompt, typed `help`, `ls`, `run /bin/doomd`, engine init, level load, first DOOM frame marker) on the real Qwen3.5 checkpoint (Qwenputer circuit, executor path), every token compared with a lockstep oracle.
Date of the run: 2026-11-04. Provenance tier: T2 (model) with the T1 reference machine as oracle, as in `docs/LIVE_DEMO.md` / `PROVENANCE.md`.

## Result

| | |
|---|---|
| Flow verified on the model | cold boot, prompt, `help`, `ls`, `run /bin/doomd`, `doomd` init lines, `DOOMD_LEVEL_START e1m1`, first frame marker (0x02) |
| Guest instructions executed by the model | 3,335,072 (of 3,335,094 total; 22 are host-executed boundary instructions, see below) |
| Segments (one Qwen turn each) | 26 for the first frame (24 key/park segments incl. cold boot, 2 level-load pieces); 27 with the extra frames |
| Chunks (parallel Modal A100s) | 3, plus 1 chunk for the extra frames (below) |
| Chip tokens produced by the model | 4,693,602 (planned 4,693,316; the few extra per segment are the ebreak/HALT record) |
| Divergence from the oracle | none (driver exits on the first mismatching token; all segments report ok; BYTE tokens equal the console bytes) |
| Console bytes under the model | 273, byte-identical to the C emulator (`rv32_fast`) and the Python reference |
| Wall time | longest chunk 561 s of driver time (602 s container); the 3 chunks ran concurrently, ~10 min end to end plus image start |
| Throughput | 3.1 to 3.4 k chip tokens/s per A100 with the K-token driver (`--k-graph 64`), 2.2 to 2.4 k instr/s |

Extended run (same plan, 4th chunk `f3`): frames 1 and 2 after the first frame, also model-verified, zero divergence. Totals for the whole typed flow from cold boot to the third frame marker: **8,239,190 guest instructions on the model, 11,708,652 chip tokens, 27 segments, 4 chunks (3 + 1), 4 Modal A100s, about $2 of GPU at list price (estimated, not billed-checked)**. Wall: the first three chunks ran in parallel in about 10 min, the extra-frames chunk (one 4.9M-instruction segment that cannot be split further) took 30.5 min, started right after.

## Who does what (host versus model)

Model (every one of these is a chip token checked against the oracle): all 3,335,072 instructions between host boundaries, including the kernel boot, the shell reading each typed key from the ring, echo, command parsing, `ls`, `run`, loading `/bin/doomd`, engine init and the level load. The guest console bytes are emitted by the model and compared.

Host (what a keyboard forwarder / disk / display does):

1. Keys. The host writes each typed character into the key ring and nothing else (mechanism below). It delivers one key each time the guest arrives at `qos_key_park` (pc 0x40044), which is exactly what `rv32_fast -K` with `shell_ready` does and what a person typing at the prompt does. 23 keys: `help\n` `ls\n` `run /bin/doomd\n`.
2. At each such boundary the host also executes the single `ret` at the park pc (the host-executed boundary instructions; the total of host-executed instructions is 22 = 3,335,094 minus 3,335,072 model instructions; the model executes everything else).
3. Disk blocks. The build is a chunk-ROM build (`-DQ_CHUNKROM`, plan base 0x29000): the host installs the data-ROM window of the disk extents the plan says the first four frame markers need, before the first segment, so zero disk requests happen inside the model segments (the plan for markers 0..3 has 0 requests). That is the same "host serves disk blocks" arrangement as the published clip, done ahead of time instead of per request.
4. Display: none in this run (no pixels; the frame marker is the evidence, as in the 3 s clip).

## Key delivery: mid-segment or boundary?

Honest answer: keys are delivered at segment boundaries, but the boundaries are placed by the guest, not by a host schedule. The driver (`tools/model_doom_qwen.py --type TEXT`) puts a ROM `ebreak` at `qos_key_park`; the model runs until the guest reaches the park (the guest is waiting for input), the segment ends there BEFORE the `ret`, the host pushes the next char through the key ring, runs the `ret`, and the next segment starts from that state. So every key is present in the guest input at exactly the instruction where the emulator reference consumed it (same instruction count: the key is published at the park, before the poll, as `rv32_fast -K shell_ready` does). Nothing is injected inside a model segment: mid-segment writes into the model's RAM are not possible with the segment/snapshot design, and with `shell_ready` they are not needed because the guest is idle at each park.

Key ring write (as `tools/keysched.py` documents): mailbox `{u32 seq, u8 q[4]}` at 0x154; write `q[seq & 3]` at `0x158 + (seq & 3)`, then `seq + 1` at 0x154 last. The kernel key counter (0x140) advances in the guest as it consumes the key. Both the model's start snapshot and the oracle copy are cloned after the write, so the model and oracle see the same keys.

The typed flow was NOT run with any key delivered while doomd is running: there are no keys after Enter in this run (the game is not yet receiving gameplay input before frame 0).

## Build and inputs (important caveats)

- ELF `build/demo/qwenos-live-e1m1.elf` md5 `f1c28a1589a4d9c63818858eae71ec23`, kernel `kernel-live.elf` md5 `d01af2d6b4162ae7865346fc8dd5706d`, chunk-ROM plan `live-crx-plan.json` md5 `fabc747c63d90812ab99cdad4204e02d` (base 0x29000), disk `E1.img` md5 `6287a13cc1079b697e1885f8f6327e06` (the same disk image as the published 3 s clip). Non-Zba build.
- This ELF is the one built on 2026-11-03 20:19 by the `CHUNKROM=1 make demo-live` flow in the `wt-merge` working tree (`/Users/jhome/qwenos-work/wt-merge/repo`), not rebuilt on this branch (the `.deps` engine tree is not present here and the time budget did not allow a rebuild). Its shell is the older shell: `help` prints `?` and `ls` lists the RAMFS (the current `docs/LIVE_DEMO.md` transcript shows a longer `help`). The typed flow, the kernel, `/bin/doomd` and the model run are real; the text of `help` is whatever that shell prints.
- The three typed commands were `help`, `ls`, `run /bin/doomd` only (no `cat`/`echo` tour).
- Checkpoint: merged Qwen3.5-4B "rv1" on Modal volume `qwenos-q4-rv1`, executor path, patched qwenputer copy with the `deque` lockstep fix (`out/model/qwenputer_patched`), K-token driver (`--k-graph 64`, commit 7d20aef on perf/ktoken, bit-exact blocks).

## Method

1. One host pass on the Python reference machine (`--dump-starts`) pickles the start state of every segment (about 15 s for the whole flow). Segments: one per typed key (ends before each park), then the level-load run split by instruction count (`--split-steps 1112000,2224000`: stop before the first pc not yet executed in that segment) into three pieces.
2. Chunks run in parallel on Modal A100s (`tools/modal_typed_chunks.py`): each `--segment-range A:B --load-starts` runs the real model on its segments with the lockstep oracle (`chat.generate(lock=...)`, every token compared; a mismatch aborts). After each segment: oracle instruction count equals the plan, model BYTE tokens equal the host console bytes.
3. Stitch: segment ranges tile the plan exactly once; console bytes of the chunks concatenated are compared with the emulator reference console (equal).

## Per-chunk table

| Chunk | GPU | Segments | Instr | Chip tokens (model / planned) | Text tokens | Console bytes | Driver wall | Result |
|---|---|---|---|---|---|---|---|---|
| t0 | A100-SXM4-40GB (Modal) | 1:25 (cold boot, 23 typed keys, first 1.24M instr of doomd init) | 1,246,050 | 1,766,142 / 1,765,878 | 968 | 272 | 561 s | all 24 ok |
| t1 | A100-SXM4-40GB (Modal) | 25:26 | 1,031,152 | 1,460,263 / 1,460,252 | 29 | 0 | 430 s | ok |
| t2 | A100-SXM4-80GB (Modal) | 26:27 (to the first frame marker) | 1,057,870 | 1,467,197 / 1,467,186 | 30 | 1 (0x02) | 479 s | ok, 1 frame marker |

Per-segment results: `docs/research/typed-flow/t{0,1,2}.result.json` (`segment_detail` = `[segment, ok, markers, instr, planned tokens]`).

## Console transcript produced under the model

```
$ help
?
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
$ run /bin/doomd
doomd: DMC100-Doom on QwenOS
doomd: img_init -> 0
doomd: image bytes 3890048
doomd: engine init done
doomd: R_Init/P_Init done
DOOMD_LEVEL_START e1m1
<0x02 frame marker>
```

Concatenation of the chunk consoles (`t0`+`t1`+`t2`) equals the emulator reference console (md5 `1a1a88291a5107a9d71d8ca23e0b662b`, 273 bytes) byte for byte.

## Extra frames

Chunk `f3` (segment 27, from the first frame marker to the third): one segment, 4,904,118 instructions, 7,015,050 chip tokens (planned 7,015,039), 91 text tokens, A100-SXM4-40GB, 1,830 s driver wall (container 1,871 s), 3.8 k chip tokens/s, 2.7 k instr/s, 2 frame markers, zero divergence. Result: `docs/research/typed-flow/f3.result.json`.

Why one segment: inside a frame every pc has already executed in the segment, so no "fresh pc" exists to put a breakpoint on for an instruction-count split (the `isplit` mechanism only works while new code is executing, e.g. level load). Splits are only possible at frame markers, and `--frames 2` fails in the driver ("no fresh breakpoint pc") for the same reason, so frames 1 and 2 are one 4.9M-instruction run.

Console of f3 (after the first marker): `DOOMD_FRAME 1 tic 1`, marker, `DOOMD_FRAME 2 tic 3`, marker, `DOOMD_FRAME 3 tic 5`. The emulator reference (`rv32_fast -F 3`, same typed schedule, console `docs/research/typed-flow/console3.ref.bin`, 315 bytes) stops at the third marker; the model segment ends at the first not-yet-executed pc after the third marker, so it prints 20 more bytes (`DOOMD_FRAME 3 tic 5\n`) and runs about 15 k instructions further (model segment ends at step 8,239,213, the emulator's third marker is at step 8,223,777). The first 315 bytes of the model console (t0+t1+t2+f3) are identical to the emulator's.

No gameplay keys were typed during these frames (the host forwarded no key after the final Enter). The frame number in "DOOMD_FRAME N" lines is the engine's own counter.

## Reproduce

```sh
# 1. typed-flow image + chunk ROM (this run used the pre-built image listed above; with the engine tree: CHUNKROM=1 make demo-live)
# 2. reference + start states (no GPU, ~15 s). PYTHONPATH = qwenputer/experimental/riscv
python3 tools/model_doom_qwen.py --dry-run --elf build/demo/qwenos-live-e1m1.elf --kernel-elf build/kernel-live.elf \
  --disk E1.img --target boot-frame --snapshot-marker 0 --frames 1 --rom-plan build/demo/live-crx-plan.json \
  --sym-elf build/demo/qwenos-live-e1m1.elf --type 'help\nls\nrun /bin/doomd\n' --split-steps 1112000,2224000 \
  --dump-starts snaps --out ref_console.bin
# 3. stage bundle (build/, tools/, E1.img) into Modal volume qwenos-bundle:/typed and snaps into qwenos-snaps-typed:/ , then
QOS_QWENPUTER=<patched riscv dir> modal run tools/modal_typed_chunks.py --tag typed1
# 4. compare: cat t0/console.bin t1/console.bin t2/console.bin | cmp - ref_console.bin
```

## Limits (plain)

- Not interactive: the text was scripted and delivered by the host at the parks; a person typing would be the same protocol, but this run is a recording of a fixed schedule.
- Frame pixels are not produced or checked here (frame markers only).
- 22 boundary instructions are executed by the host, not the model.
- Disk is served by chunk-ROM windows installed by the host before each segment, not per request.
- The `help` output is the old shell's `?`.
- Time per frame: the first DOOM frame is 3.3M instructions after boot; later frames cost about 2.4M instructions each (measured: 2.43M and 2.46M).
- Frame-by-frame key delivery during gameplay (`frame N <key>` schedule lines) is not implemented in the model driver; only the shell-park protocol is.
