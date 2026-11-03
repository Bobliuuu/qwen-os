# QwenOS v0.8 — a RISC-V operating system experiment for Qwenputer

QwenOS targets the **RV32IM CPU compiled into Qwenputer's transformer layers**:
https://github.com/divagr18/qwenputer. The long-term goal is to run a genuine
DOOM executable **as an application of an operating system**, rather than as
standalone DOOM firmware. Architecture is inspired by
https://github.com/Bobliuuu/bobliu-os, but the CPU and memory limits differ.

## Verified now

- A freestanding C RV32IM kernel, booted as a Qwenputer-layout ELF on an
  **independent Python reference interpreter** (NOT a GPU model run).
- Four independently linked ROM application ELFs: shell, paint, raycaster,
  and WAD-asset test (plus the separate kernel ELF). All guest control flow executes as RISC-V
  instructions; the guest raycaster is **not** DOOM.
- Guest API v1 with file operations, basic RAMFS, nested application entry,
  independent bounded invocation stacks, keyboard mailbox, 32×24 framebuffer,
  scanline copies and a present/checksum function.
- Read-only virtual disk mailbox (256 bytes per request, bounded guest buffer,
  sequence-numbered request/response, cancellation and bounds/error checks).
- Guest WAD file parser proof: reads 12-byte IWAD header, 16-byte directory
  entry at 0x300000 and a 32-byte lump at 0x210000, through the **kernel API**.
  The host only transfers requested bytes. This runs against a synthetic
  4-MiB WAD fixture; it is NOT commercial DOOM game data.
- **15 Python regression tests passing** including genuine RV32 guest execution,
  disk requests, invalid reads and a Qwenputer-word-RAM mailbox adapter.

## Build and test (Clang/LLD + readelf + Python 3)

```sh
make clean && make check
make frame
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
**we could not run the upstream package here** because it is not installed
and network fetching is unavailable.

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
  five ROM-linked programs (kernel and four applications).
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
