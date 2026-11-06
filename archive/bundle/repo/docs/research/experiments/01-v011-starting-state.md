# 01 v0.11 starting state

Goal: record the baseline everything else builds on.

State (from `/Users/jhome/qwenos-work/bundle/repo/README.md`, git history `d54e742`, `3ffa7c8`, `a10465d`):
- Freestanding RV32IM kernel; six ROM-linked ELF regions (kernel, shell, paint, raycast, asset, WAD viewer) in the 256 KiB exec ROM.
- 32 KiB RAM map: kernel stacks, small RAMFS, fds, 8-byte keyboard mailbox, 32x24 framebuffer, 256-byte disk mailbox.
- Host-as-storage 256-byte block device; WAD directory scanner; DOOM-WAD map viewer (v0.9: untextured 32x24 ray cast over linedefs).
- Independent RV32 emulator in Python plus `tools/rv32_fast.c`; synthetic WAD fixture; `make check` (29 tests in the v0.11 README text, 32 after v0.12, 35 after the RAM squeeze).
- Upstream Qwenputer CPU had never been run on QwenOS; no model run; README states explicitly "not a DOOM port".
- v0.10 reclaimed 9,216 B by cutting application stacks from 8x1536 to 2x1536; WAD app RAM became 22 KiB (0x1800..0x6fff).

Result: baseline. Inconsistency noted: the README quotes 29 tests in one section and 32 in another (v0.12 appended without rewriting the earlier text).

Files: `README.md`, `kernel/`, `apps/`, `tools/`, `tests/` of the main repo.
Reproduce: `make clean && make check` (not re-run for this record).
Evidence: TRACES/merge/check.log shows a recent `make check` fragment from the merge tree (boot script output, PASS lines).
