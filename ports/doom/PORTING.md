# Genuine DOOM engine port — integration contract

This folder is an OS-device HAL used by the WAD map viewer. It is not an
engine port. For playable DOOM, use the original GPL DOOM engine or the
32-KiB-RAM DMC100-Doom fork, not this viewer as a replacement.

## Host/guest trust boundary

- The guest executes RV32IM instructions in the Qwenputer circuit.
- The kernel owns file descriptors, input, display, application stack, and
  the mailbox; the engine calls `qos_doom_wad_read`, `qos_doom_present8` and
  `qos_doom_key`.
- A host may provide **only block data** for the guest disk. It must not parse
  WAD lump structures, perform collision, update game state, or render pixels.
- For an all-in-model configuration, the disk mailbox must instead be
  serviced by Qwenputer's DeltaNet storage or a model-side device circuit.

## Specific incompatibilities with upstream DMC100-Doom

1. Its MCU is ARM Thumb, not RV32IM. Full engine source and support libraries
   must be rebuilt with the RISC-V clang target; the binary cannot be reused.
2. Its 42-KiB execute-from-RAM overlays are not executable on Qwenputer P3.
   Re-link overlays into the 256-KiB ROM, or extend Qwenputer CPU and compiled
   weights to fetch instructions from RAM. Re-linking is preferable for a
   fixed engine if the final RISC-V image fits.
3. Its original asset converter creates device-specific `DOOM.DAT` data,
   not normal WAD structures. The existing QwenOS virtual disk works for
   unmodified WAD bytes but does not yet implement the converted asset format.
   Port `w_file` and pack-reading code appropriately.
4. The 32-KiB RAM limit includes QwenOS kernel, stacks, mailbox and graphics.
   The compiled engine must be linked as a new ROM application with its
   writable state in the per-application RAM region. The RAM-use linker map
   must be audited and bounded before activation.
5. The current 32x24 8-bit framebuffer is extremely low-resolution. The
   renderer should output strips/scanlines, not a full 320x200 framebuffer.
6. The model's trace rate is orders of magnitude slower than conventional CPU
   frame rates. Start with one E1M1 frame on the official reference CPU,
   then test the actual merged checkpoint, before any realtime target.

## Acceptance tests for a genuine engine port

- Reproducible cross-build of unmodified GPL gameplay logic with only
  documented hardware/platform adaptations; retain license notices.
- Compile and boot it as `/bin/doom` through QwenOS instead of substituting
  a bespoke WAD raycaster.
- Independently verify vanilla-compatible game ticks/DEMO1 against upstream
  oracle with a legally redistributable Freedoom IWAD.
- Validate game-state updates, player input and at least one rendered frame
  on Qwenputer's *official* CPU reference, not just the independent emulator.
- Generate and check an exact compiled-circuit trace from the merged Qwenputer
  checkpoint with the game running. Document any external-storage assistance.

References:
- https://github.com/ArturBieniek4/DMC100-Doom (GPL-2.0)
- https://github.com/ozkl/doomgeneric (GPL-2.0)
- https://github.com/divagr18/qwenputer
