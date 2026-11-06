# Compiler bench / Zba gate notes (hybrid: Qwen text turn + in-weight chip)
Zba gate PASS on q4-rv1 (A100-SXM4-40GB, driver k-graph 64, lockstep, slow_blocks 0, zero divergence):
- COMBINED ELF (out/combined), segs 1:4, split-steps 250000: 255,094 instr, 352,219 chip tokens, 181.5 s, 1940 tok/s (short run, incl. warmup).
  Ref machine: first SH?ADD at step 90,219 (pc 0x6fd20); 9,399 SH?ADD executed inside the window.
- TUNED ELF (branch perf/compiler, plan base patched to 0x29000), segs 1:4, split-steps 1708864: 1,752,465 instr, 2,488,569 tokens,
  747.6 s, 3329 tok/s, 2344 instr/s on A100-SXM4-80GB (node was 80GB); first SH?ADD step 90,342; 47,925 SH?ADD in window; 0 mismatches, slow_blocks 0.
- OLD ELF same flags: 1,819,896 instr, 2,564,928 tokens, 748.6 s, 3426 tok/s, 2431 instr/s on A100-SXM4-40GB (split by step count, NOT same game work).
- Equal work (reference-machine dry plan, boot to first frame marker): OLD 3,417,726 instr / 4,797,431 tok; TUNED 3,137,708 / 4,442,339 (-8.2% instr, -7.4% tok).
- BUG in branch: tools/chunkrom.py CRX_BASE=0x28C00 but guest Q_CRX_BASE=0x29000, so its crx-plan.json base is wrong -> ref/driver faults (load out of range) at step 90,380. Fix: base=0x29000 in json (regenerated with budget 0x16000).
Logs: perf/cb_old_A100.log cb_new_A100.log cb_comb_gate.log. Files: scratchpad perfnew/, comb/; Modal vol qwenos-bundle /perfnew /perfcomb.
