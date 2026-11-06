# 04 doomgeneric (vanilla DOOM) feasibility

Goal: decide whether stock doomgeneric can run on the Qwenputer RV32IM target.

Method: cross-build vanilla doomgeneric to rv32im with clang and read the linker map (prototype glue in `/Users/jhome/qwenos-work/engine/port/`: `hal.c`, `qlibc.c`, `qplat.c`, `rtlib.c`, `engine.ld`, `link.sh`; full map `van_qos.elf.map` 527 KB not copied; sources under `engine/vanilla`, `engine/doomgeneric`).

Numbers: text 168 KiB (repo README v0.12; the agent report adds bss about 240 KB and a 6 MB zone allocation). Text would fit the 256 KiB exec ROM after stripping. RAM is the blocker: 32 KiB total versus hundreds of KB.
Result: no-go for RAM. Did not proceed; the DMC100 port (experiment 07), designed for a 32 KB-RAM MCU, was chosen. README v0.12 states a DMC100-style port needs about 21.7 KB minimum, which required reclaiming kernel `.bss` (experiment 06).
Files touched: none in the main repo (prototype only in `engine/port`).
Reproduce: not reproducible without the prototype dir; `engine/port/link.sh` (unverified).
