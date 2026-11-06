# 10 Syscall squeeze (sys.patch)

Goal: sys_entry was 10.1 % of instructions (108,199 calls at 85.7 instr each in the profile). Shorten the takeover syscall path.

Method: trusted takeover code accesses resident core addresses directly (kernel.ld ASSERTs the addresses); framebuffer written straight into the resident 32x24 buffer (no FB_SET syscall); FB_PRESENT only computed a checksum nobody reads while doomd owns the machine, so presenting is just the frame marker; inline DISK_READ in `qplat`; console bytes go straight to the host.
Numbers (agent report): -7 % instructions.
Result: worked. Superseded in places by the RAM squeeze (framebuffer later removed from resident RAM, experiment 12) and the OS-flow leaf fast paths (experiment 15).
Files: `include/qos.h`, `kernel/main.c`, `linker/kernel.ld`, `ports/doomdmc/{doomd_main,qlcd,qplat}.c`, `qplat.h`, `tools/rv32_fast.c`.
Patch: TRACES/patches/sys.patch (md5 deb26b3690e2491c7668813a0d27f2cd). Not re-run in this pass.
