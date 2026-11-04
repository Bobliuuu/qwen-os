# 06 Kernel RAM reclaim and takeover mode (v0.11)

Goal: give the engine as much of the 32 KiB RAM as possible: 22 KiB (0x1800..0x6fff) in the WAD viewer era.

Method: `/bin/doomd` is a takeover app. `exec("/bin/doomd")` abandons shell stack and RAMFS; the app owns RAM from 0x05c0; a resident kernel core (0x100..0x5bf: input mailbox, disk mailbox, 32x24 framebuffer, state words, 128 B stack) stays. Only console, framebuffer, key, disk, getpid/yield syscalls work during takeover. On return the kernel zeroes the overlay and warm-reboots. Exec ROM repacked: kernel 4 KiB at 0x40000, doomd 0x41000..0x77fff (220 KiB), small apps 0x78000.., WAD viewer 0x7c000. Data ROM: doomd 0x21000..0x3efff (120 KiB). `crt0` copies `.data` from the ROM image and zeroes `.bss` (RAM is dirty at entry).

Numbers: app RAM 22 KiB -> 31,296 B (30.56 KiB); with a 1,536 B stack 29,760 B for data+bss. Core 1,216 B.
Result: worked (stub test `tests/test_doomd.py`). Later squeezed further (experiment 12, core 152 B).
Files: `kernel/main.c`, `kernel/start.S`, `linker/{kernel,doomd}.ld`, `apps/doomd_crt0.S`, `include/qos.h`, `tools/check_layout.py`, `tools/merge_elf.py`.
Evidence: TRACES/RAM_BUDGET_v1.txt (final v1 budget).
Reproduce: `make check` enforces the layout (`tools/check_layout.py`).
