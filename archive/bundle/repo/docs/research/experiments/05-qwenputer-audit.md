# 05 Qwenputer audit and rejected hardware ideas

Goal: find out which limits are fixed by the compiled model and which QwenOS can move.

Findings (checked against `qwenputer/experimental/riscv/chipformer/rv/spec.py` and its README):
- Memory map constants are hardwired: `ROM_BASE=0x40000, ROM_WORDS=1<<16` (256 KB code), `DROM_BASE=0x20000, DROM_WORDS=1<<15` (128 KB read-only data), `RAM_BASE=0, RAM_WORDS=1<<13` (32 KB). Also in `core.py` (agent report).
- 32 KB RAM lives in DeltaNet recurrent state. Agent report: a 1 MiB RAM would need about 1,024 heads of state versus the current small head count (the merged circuit used here reports 103 heads, 11 chip layers, hidden 3968, from `out/model/merge.log`). Rejected: not a QwenOS-level change, would require rebuilding the compiled model.
- Execute-from-RAM: the PC is `ROM_BASE + 4*(anchor+n)`; instructions come from the ROM sublayers. Rejected: cannot load overlays at run time; DMC100's 42 KB RAM overlays had to be re-linked into ROM (experiment 07).
- Speed: upstream README (`experimental/riscv/README.md` line 24) says a compact executor does about 3,700 instr/s per stream on an L4. Measured here on an A100 (executor path, lockstep oracle): about 2.2 k chip tokens/s pure plus 1.7 s per pause (agent report). Cross-check from the boot run (292 pauses, 2,091,327 tokens, 1,438 s): 2,091,327/2,200 = 951 s plus 292 x 1.7 = 496 s = 1,447 s, matching 1,438 s. End to end that is 1,454 tokens/s and 1,080 instr/s. The 3.7 k figure was not reproduced.

Result: constraints list; drove the design (everything in ROM, data in ROM, disk pauses minimized).
Files: none changed. Evidence: TRACES/model/boot.json, TRACES/model/merge.log.
