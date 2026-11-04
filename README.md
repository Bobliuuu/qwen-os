# QwenOS: a RISC-V operating system that boots DOOM, built for Qwenputer

QwenOS targets the **RV32IM CPU compiled into Qwenputer's transformer layers**
(https://github.com/divagr18/qwenputer, 32 KiB RAM, 256 KiB exec ROM, 128 KiB data ROM).
The goal is to run a genuine DOOM engine **as an application of an operating system**
(`/bin/doomd`), not as standalone firmware. Architecture is inspired by
https://github.com/Bobliuuu/bobliu-os, but the CPU and memory limits differ.

## Status (read this first)

| Claim | State |
|---|---|
| DOOM engine (DMC100-Doom, GPL-2.0, 32 KB-RAM port) builds as `/bin/doomd` and runs Freedoom E1M1 on the C emulator `tools/rv32_fast` | yes, regression-tested against goldens |
| Typed flow: boot -> shell prompt -> `run /bin/doomd` -> E1M1 with keys, all as guest RV32 instructions | yes (emulator) |
| Chunk ROM: disk reads served from the data ROM (165,054 -> 4 requests per 350 tics) | yes (emulator), costs about +10.6 % instructions |
| Real Qwen model verified a cold boot to the first frame marker (1,552,382 instr, lockstep oracle, zero divergence, A100) | yes, on a **pre-merge** build |
| Real model executed E1M1 gameplay frames / the 3 s clip | **not yet** (pending) |
| Real-time or interactive play in the model | **no** (about 1.1 k instr/s measured; a game tic costs 0.5-5 M instr) |

Boundaries: disk and keys are supplied by the host, the clock is virtual, pixels come
from the emulator while the model verifies the instruction trace, and model runs are series
of host-snapshotted segments. See `docs/research/HONESTY.md` for the full list, and
`docs/research/` (STATUS, TIMELINE, REPRODUCE, experiments 01-21) for the evidence.
`MERGE_NOTES.md` documents the final merged E1M1 build (addresses, numbers, known gaps).

## Quick start

Needs Clang/LLD, `readelf` and Python 3. No game data is in this repo.

```sh
make check          # kernel, layout, Python reference, unit tests
make demo-elf       # scripted E1M1 model-run image -> build/demo/qwenos-e1m1.elf (+ chunk-ROM plan)
CHUNKROM=1 make demo-live   # typed-flow image -> build/demo/qwenos-live-e1m1.elf
tools/qwenos_live.sh        # interactive terminal: type `run /bin/doomd`; Ctrl-] quits
```

`demo-elf`, `demo-live` and the live terminal need the DOOM engine and a WAD (steps below).
`make check` needs neither (the real-WAD tests are skipped or use synthetic fixtures).

### Engine and Freedoom (not included)

```sh
mkdir -p ../engine ../wads
git clone https://github.com/ArturBieniek4/DMC100-Doom ../engine/DMC100-Doom
(cd ../engine/DMC100-Doom && git checkout 0cdc78e && patch -p1 < "$OLDPWD/engine-patches/dmc100-qwenos-merged.patch")
# Freedoom (modified BSD): https://freedoom.github.io  -> unzip freedoom1.wad into ../wads/
```

`ports/doomdmc/mkimage.sh` builds the NOR disk image (`E1.img`) from the layout and the WAD;
`ports/doomdmc/build.sh` builds `doomd`. Override locations with `DMC`, `IWAD`, `QOS_FREEDOOM_WAD`.
The `engine-patches/` diff holds the QwenOS edits to DMC100-Doom (see `engine-patches/NOTICE`).

### Tests

`make check`; `tools/doomd_regress.sh` (state/frame goldens in `tests/golden/`); upstream
lockstep needs a checkout of qwenputer on `PYTHONPATH` (see `MERGE_NOTES.md`).
`tools/model_doom_qwen.py` and `tools/model_doom_chunks.py` drive the real model and need a GPU
box plus the Qwen checkpoint; they are not run in CI.

## License

GPL-2.0-only, see `LICENSE` and `NOTICE`. DMC100-Doom, doomgeneric and DOOM are GPL-2.0;
Freedoom is separate (BSD) and not included.

---

The sections below are the historical per-version README (v0.9 to v0.13), kept for reference.

## Current implementation (v0.11, November 2026)

**Verified locally on the independent RV32 emulator, not inside Qwen's model:**

- Freestanding RV32IM kernel and six separately linked ELF regions (kernel,
  shell, paint, raycast, asset test, WAD-map renderer) within Qwenputer's
  256-KiB read-only executable ROM. These are static guest entry points, not
  protected or dynamically loaded Unix processes.
- Two bounded, independent application stacks (the current maximum nesting), small writable RAMFS, file descriptors,
  keyboard mailbox, and 32x24 framebuffer/scanline syscall interface.
- A 256-byte request/response block device. The **host is storage hardware**;
  it does not interpret game logic. For an entirely self-contained model,
  storage would also need to be implemented inside Qwenputer's state.
- WAD directory scanner with up to 8192 lumps; THINGS, VERTEXES, LINEDEFS,
  SIDEDEFS, and SECTORS parsing. On maps fitting 768 vertices, 1024 linedefs, 1024 sidedefs, and 192 sectors it caches geometry. For larger
  maps (up to 8192 vertices and 8192 linedefs) it streams line and vertex
  records from the virtual disk without caching all geometry in 32 KiB RAM.
- A **DOOM-WAD map viewer**, with sector floor/ceiling-height-sensitive wall
  projections, rejection of malformed sector indices, WASD movement/turning,
  simple wall-crossing collision, and repeatable interactive frames. Draws
  are performed by guest RV32 instructions, with scanline framebuffer copies.
- A synthetic WAD regression fixture, not commercial game content.
- **29 regression tests pass locally** (`make check`). The multi-frame emulator
  produces three independent guest-rendered frames (`--keys wd`).

**Not implemented:** a genuine DOOM engine (BSP rendering, real textures,
monsters, collision/sliding, game state, sound, real-time play), hardware
privilege isolation, executable loading from writable memory, or model-side
WAD request handling. Local tests do NOT prove that Qwen3.5's compiled
transformer layers executed the guest. The model checkpoint and GPU are not
present in this container.

The upstream CPU's ROM is read-only: independent ROM-linked ELF applications
are supported, but dynamic process loading would require executing code from
RAM or an equivalent hardware extension. The WAD viewer is not a DOOM port.

## Build and test (Clang/LLD + readelf + Python 3)

```sh
make clean && make check
make doom-frame
python3 tools/interactive_frames.py --keys wd
python3 tools/wad_device.py build/qwenos.elf
```

The normal boot without a disk adapter remains valid and the guest reports
`asset: no disk device`. The disk-adapter run reports
`asset: WAD read and verified`, and the kernel prints `QWENOS_BOOT_OK`.

Run against any local WAD file as a block device:

```sh
python3 tools/wad_device.py build/qwenos.elf --wad /path/to/file.wad
```

Note that the asset demo specifically looks for the synthetic `QOSDEMO` lump
and will report a mismatch on ordinary DOOM WADs; **the virtual disk adapter
itself accepts arbitrary WAD bytes**. The actual DOOM engine has not been ported.

## v0.12: real-WAD BSP viewer

`/bin/doom` now renders Freedoom 0.13.0 `freedoom1.wad` E1M1 (fetch separately;
tests skip if absent, override via `$QOS_FREEDOOM_WAD`): guest-side streamed
NODES/SSECTORS/SEGS front-to-back BSP traversal, per-column clipping, sector
light/sky shading, BLOCKMAP collision with step/headroom checks. ~225-290K guest
instructions per frame on the reference emulator. Still a 32x24 flat-colour map
viewer: no textures, sprites, monsters, doors, ticks or sound. `make check`: 32 tests.

**Engine port feasibility:** vanilla doomgeneric on rv32im is ~168 KiB text (fits ROM
after stripping) but needs far more than 22 KiB RAM; a DMC100-style port needs ~21.7 KB
minimum, so it would require reclaiming kernel `.bss`. Not started.

## Upstream CPU verification

With Qwenputer checked out, run its **real upstream reference CPU**:

```sh
PYTHONPATH=/path/to/qwenputer/experimental/riscv \
  python3 tools/upstream_ref.py build/qwenos.elf --wad-device
```

Omit `--wad-device` to test no-device boot. Use `--wad /path/to/file.wad`
to supply a real WAD. The tool uses upstream `chipformer.rv.elf.program` and
`chipformer.rv.ref.Machine` and writes replies through the real reference
machine's RAM word array. The adapter's memory logic is locally tested;
**Verified (2026-11-03):** upstream `ref.Machine` boots QwenOS with the WAD
device (exit 0, `QWENOS_BOOT_OK`, 120,267 instructions, ~173k chip tokens) and
`tools/upstream_probe.py` passes park/resume. Note upstream `generate()` defaults
to `max_chip=60000`, so a full boot needs a larger chip-token budget on the model
path. No GPU/checkpoint run has been done.

## DOOM platform HAL and genuine-engine status

The `ports/doom/hal.{h,c}` layer now implements the actual QwenOS device
contract required by a native DOOM engine: 256-byte paged WAD reads,
8-bit framebuffer scanline presents, and guest keyboard polls. The existing
WAD geometry application now uses this shared layer. This gives us a real
OS-device integration point instead of duplicating syscalls inside the viewer.

**This is NOT a genuine DOOM engine port.** The required engine gameplay,
BSP, textures, sprites, and sector machinery from id's GPL source or the
DMC100 memory-constrained port are absent. DMC100-Doom uses external code
overlays and preconverted assets; Qwenputer does not execute from RAM. A
real port must prelink code into the ROM, or modify Qwenputer's compiled
CPU. Model-side WAD device servicing also requires pausing and updating
DeltaNet RAM snapshots between generated trace bursts. Neither of those
features has yet been verified on the merged model.

## v0.11 model-side handshake

The firmware `build/qwenos-model-probe.elf` is compiled directly from the
**same QwenOS kernel implementation** with `QOS_MODEL_BRIDGE`. It runs the
kernel startup, then intentionally parks at `ecall a7=93`, without output.
When a Qwenputer tool call resumes it, it executes `QOS_SYS_FB_SET`,
`QOS_SYS_FB_GET`, validates the ABI and PID, and emits the special Qwenputer
`<tool_response>` and `</tool_response>` tokens (BYTE payloads 256/257)
surrounding `QWENOS_MODEL_PROBE_OK`. The second exit parks it again.

Build and test park/resume **on an independent CPU**:

```sh
make model-probe
```

Run it against **upstream's official reference CPU** (not Qwen's weights):

```sh
PYTHONPATH=/path/to/qwenputer/experimental/riscv \
  python3 tools/upstream_probe.py build/qwenos-model-probe.elf
```

Run it **inside Qwenputer's actual merged checkpoint** (GPU and Qwenputer
Python environment required):

```sh
PYTHONPATH=/path/to/qwenputer/experimental/riscv \
  python3 tools/model_probe_qwen.py /path/to/Qwen3.5-4B-Qwenputer \
  --elf build/qwenos-model-probe.elf
```

The model test uses Qwenputer's own `RvChat.generate`, its compiled layers
and an upstream reference lockstep oracle. It checks for marker, zero
lockstep divergence, and zero compiled-circuit head mismatches. It is **not**
a full OS/model boot (no process or WAD disk on this path yet), and cannot
be verified without the checkpoint and GPU. Never confuse `make model-probe`
with neural execution.

## Actual Qwen model execution

Qwenputer's public code provides a `chipformer.rv.firmware` standalone
compiled-circuit runner that accepts an ELF, but it needs a compatible RV-tiny
checkpoint. The published merged Qwen3.5 chat model expects a text tool-call
bridge and is NOT interchangeable with the standalone runner.

No execution inside the compiled model or end-to-end lockstep against its
transformer circuits is claimed for QwenOS yet. Also, our device adapter
modifies a guest RAM snapshot in the reference interpreter; equivalent
**pause / patch / resume** injection into the compiled model's recurrent state
still needs integration with Qwenputer's runner. The external WAD storage is
**not itself stored inside the model**.

## Address map / limitations

- Qwenputer RAM 0x00000–0x07fff: 32 KiB; the guest kernel maintains stacks,
  framebuffer, and disk request/reply mailbox in this region.
- Data ROM 0x20000–0x3ffff: 128 KiB read-only.
- Executable ROM 0x40000–0x7ffff: 256 KiB, partitioned at build time into
  six ROM-linked regions (kernel and five application ELFs).
- The hardware has no privilege levels, memory protection, timer interrupt,
  or execute-from-RAM. These applications are not isolated Unix processes;
  their binaries are prelinked at fixed ROM addresses and their syscalls
  use a guest function pointer, not a hardware trap.
- The keyboard and disk are virtual-device adapters; no hardware devices
  exist inside the stock compiled circuit.

## DOOM roadmap

1. Reproduce the same boot and disk test with upstream Qwenputer `ref.Machine`.
2. Run on the compatible compiled model, validating the trace against the
   reference machine and implementing pause/patch/resume for disk I/O.
3. Adapt a GPL DOOM engine or a documented memory-minimized port to the
   QwenOS filesystem, framebuffer, key, and WAD paging interfaces.
4. Add a real frame buffer resolution / strip-renderer strategy, dynamic
   memory planning and sufficient instruction budget; optimize later.
5. If the goal is *all state inside the model*, add in-model WAD storage and
   paging. An external read-only block device is an ordinary OS boundary,
   but is not an entirely in-weights game.

## v0.9: WAD-backed wall rendering from a separate guest executable

- Added `/bin/doom` (ROM `0x7c000`), independently linked from the kernel,
  with its own writable scratch section in RAM `0x4000..0x4fff`.
- Guest code reads `IWAD`/`PWAD` headers, finds `E1M1` or `MAP01`, walks the
  16-byte lump directory, decodes standard 4-byte `VERTEXES`, 14-byte
  `LINEDEFS`, and 10-byte `THINGS` entries, including the player-1 start.
- Casts rays against WAD linedef segments and paints a **32x24 untextured
  first-person wall projection**, using the kernel framebuffer syscalls.
  One keyboard event can change viewing direction.
- The included `doom_fixture()` has a synthetic E1M1 room at offsets above
  2 MiB and its directory above 3 MiB. This is a minimal *format-compatible
  map fixture*, not a complete playable IWAD or original DOOM assets.
- `make doom-frame` runs all of this as guest RV32 instructions and saves
  `build/doom-frame.pgm`. The artifact can be enlarged with nearest-neighbor
  scaling for inspection.
- The boot remains healthy when no disk device is available or map geometry
  is malformed. Tests include corrupt linedefs, missing valid header,
  rendered pixels and keyboard-driven frame differences.

**Still NOT the DOOM engine:** there is no BSP/sector-height handling, textures,
collision, sprites, sound, game simulation, or continuous input loop. The
bounded in-RAM geometry cache currently supports up to 64 vertices and 96
linedefs, and thus does not yet support ordinary large stock DOOM maps.
The next required work is a real DOOM engine integration or an incremental
streaming renderer large enough for real maps; do not claim playable DOOM.

No test here executes the model checkpoint itself. The `upstream_ref.py` path
also remains unverified until the Qwenputer source dependency is installed.

## Exact acceptance gates for the requested end goal

1. `make check` passes on the independent interpreter (done).
2. The `upstream-qwenputer-reference` CI job passes using **Qwenputer's own**
   `chipformer.rv.ref.Machine` against the identical QwenOS ELF (not yet run).
3. A compatible checkpoint (not the chat bridge alone) produces the same
   instruction trace/guest output as Qwenputer's reference machine (not run).
4. Qwenputer model-side memory state supports block-device request/response
   pause and resume without letting the host execute guest instructions.
5. A genuine GPL DOOM engine is ported to the guest API and runs with
   appropriate game assets, correct simulation and rendered game frames.

The CI workflow added here verifies (2) automatically **after the user pushes**
these files. It does not validate model (3). If (2) fails, the official
reference CPU and this interpreter are not compatible and that bug must be
fixed before claiming any model-side results.

## Interactive guest-frame reproduction

```sh
make check
python3 tools/interactive_frames.py --keys wd
# build/interactive-00.pgm, -01.pgm, -02.pgm: raw 32x24 guest frames
```

All three frames are generated by guest RV32 application instructions. The
host injects one key into an input mailbox after each frame completion
notification, copies the guest framebuffer, and serves read-only WAD bytes.
This is a deterministic **headless reference emulator** demo, not interactive
realtime Qwen3.5 inference and not the actual DOOM gameplay renderer.

The cached geometry path is much faster than the streaming path. The
regression fixture with 800 vertices and 140 linedefs exceeds the cache and
uses the streaming path. This is likely
prohibitively costly for full levels under present transformer inference.
A proper BSP traversal and asset-cache/paging strategy are required before
production maps can be efficient.

## Live shell, typed keys, one-command terminal (v0.13)

The OS can now be driven like a machine with a keyboard. `make live` builds `build/qwenos-live.elf`
(kernel `-DQOS_LIVE` + `-DSHELL_LIVE` shell; the boot-script kernel/shell used by the old tests are unchanged).
Cold boot prints **no banner**: the first thing the guest does is print `$ ` and park in `KEY_WAIT`
(184 instructions after reset). The shell (apps/shell.c, 2 KiB of its 4 KiB slot) echoes typed characters via
PUTC, handles backspace/Enter and runs `ls`, `cat F`, `echo a b [> /tmp/note]`, `run /bin/X`, `exit`;
`run /bin/doomd` takes over RAM and, in the mode-3 doomd, starts straight at **E1M1** and then plays on whatever keys
arrive (w/s move, a/d turn, f/space fire, e use, p = dump the next frame over PUTC).

**Run it (one command)** - needs `make live`, the DMC100 NOR image and a doomd mode-3 image
(`OS=live ports/doomdmc/mkmode.sh 3`; the launcher builds what is missing):

    tools/qwenos_live.sh            # type: run /bin/doomd <Enter>      (add --auto to have it typed for you)
    # Quit: Ctrl-]  (or Ctrl-C). Arrow keys are sent as w/s/d/a. --fps N paces the display (default 35, 0 = unlimited)

The host (`tools/rv32_fast -L`) does only three things: raw tty keystrokes -> guest keyboard mailbox (flow-controlled by
the guest's read counter), serving E1.img blocks, and display: guest PUTC bytes are the console and, once DOOM prints
frame markers, the guest's 32x24 kernel framebuffer is drawn with 24-bit ANSI colours from the real PLAYPAL
(`--wad`, default freedoom1.wad; half-block characters when the terminal is short). Prompt, echo, `ls`, `run`, DOOM and
all game logic are guest RV32 instructions. On exit it prints the guest instruction count and frames shown.
The 32x24 framebuffer is what the guest always maintains; full 320x240 frames exist only through the `p` dump (tools/os_demo.sh).

**Keyboard mailbox** (include/qos.h): 8 bytes at 0x154 (merged build; qos_input_mailbox), a 4-deep ring: `u32 seq` + `u8 q[4]`; push = write
`q[seq&3]`, then `seq+1` (last). The kernel's read counter lives in core RAM, so keys survive `run /bin/doomd`
(exec/takeover) and queue while the engine is busy; `KEY_POLL` pops the oldest, `KEY_WAIT` parks until one arrives.
**Scripted keys / model driver protocol**: `-K schedule.txt` for rv32_fast and `tools/keysched.py` for the Python
reference (`shell_ready <key>`, `frame N <key>`, `<instr> <key>`); keysched.py documents the exact mailbox
address/value writes and pause points (pc == `qos_key_park`, a single `ret`, one key pushed per park).
`tools/os_demo.sh` replays boot -> typed `run /bin/doomd` -> E1M1 -> simulated play, prints instruction counts and writes PNG frames.
Tests: `tests/test_shell_live.py` (Python reference CPU + rv32_fast), `tests/test_live.py` (pty-driven human session).

Measured (rv32_fast, instructions; run tools/os_demo.sh to reproduce): cold boot -> prompt 184; typing the 15 keys of
`run /bin/doomd<Enter>` 1,050 (70 each); Enter -> doomd_main 2,509; doomd init to level start 130.5K; level load + first frame 3.60M;
**total cold boot -> first E1M1 frame 3.73M** (was 3.92M with the old boot script + doomd mode 2 on the same perf tree); later frames
about 2.7M each with keys. Savings came from: no bss byte-clear loop at boot (22K), no boot script/banner, doomd's RAM
zeroing moved to the kernel (only the 4.4 KB overlay when only the shell ran; saves 25K+), table CRC for the
image header (-29K), direct framebuffer writes (FB_PTR, about -30K per frame), leaf fast paths for PUTC/KEY_WAIT/DISK_READ.

## 32-KiB RAM budgeting (v0.10)

The kernel originally reserved 8 * 1536 = 12,288 bytes for application stacks,
although this firmware has no preemption and currently runs only the shell and
one child at a time. It now reserves 2 * 1536 = 3072 bytes, returning 9216
bytes to the memory budget. A linker assertion confines all kernel static
memory to RAM below `0x1800` (the actual last symbol is checked at build).

The WAD application now has `0x1800..0x6fff` (22 KiB) for static data, and the
kernel stack is reserved at `0x7000..0x7fff`. Kernel RAM occupancy and ELF
segment overlap are checked by the build and regression tests. This increases
the normal geometry cache substantially, but **does not make a full DOOM
engine fit automatically**: the port still needs asset streaming, heap
budgeting, executable ROM repacking, and possibly a larger compiled RAM.

A candidate upstream engine is `ArturBieniek4/DMC100-Doom`, a genuine GPL
DOOM-derived engine optimized for a 32-KiB-RAM embedded system. Its current
firmware architecture uses externally loaded overlays and several megabytes
of flash. It cannot simply be linked into our current 16-KiB `doom` ROM slot
or loaded as runtime code on stock Qwenputer, whose ROM is immutable. Porting
it requires rebuilding its platform layer and repacking the ROM/overlays.

## /bin/doomd takeover mode and RAM map (v0.11)

`/bin/doomd` (exec ROM `0x41000`, entry `app_main` from `apps/doomd_crt0.S`) is a
*takeover* app: `exec("/bin/doomd")` (or `-DQOS_BOOT_DOOMD` kernel, `make
build/qwenos-doomd.elf`) abandons the shell stack and RAMFS and gives the app all
RAM from `0x0570` to `0x8000` (30,800 B), with its stack growing down from `0x8000`.
Resident kernel **core** (`0x100..0x56f` behind a zero null guard `0x00..0xff`; fixed addresses: takeover stack 0x100, state 0x140, input ring 0x154, disk mailbox 0x15c, 32x24 framebuffer 0x270): the normal kernel stack lives in the overlay. While doomd runs only
console, framebuffer, key, disk and getpid/yield syscalls work (file syscalls
return -1). When doomd returns the kernel zeroes its overlay and warm-reboots
(RAMFS content is lost). RAM is dirty at entry and `.data` is not preloaded:
crt0 copies `.data` from its data-ROM image and zeroes `.bss`.

Exec ROM was repacked: kernel `0x40000` (4 KiB), doomd `0x41000..0x77fff`
(220 KiB), shell/paint/raycast/asset `0x78000..0x7bfff` (4 KiB each), WAD viewer
`0x7c000`. Data ROM: kernel `0x20000`, doomd `0x21000..0x3efff` (120 KiB),
small-app rodata `0x3f000..0x3ffff`. See `linker/doomd.ld`,
`include/qos.h`, and `tools/check_layout.py` (enforces all of this).
