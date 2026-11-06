# 20 Real-model runs on the Lambda A100

Setup: Qwen3.5-4B merged "rv1" checkpoint (circuit: 11 layers, 2,918 dims, 103 heads, 42,114 FFN units; slots 1,265, hidden 3,968; from TRACES/model/merge.log), A100-SXM4-40GB (Lambda <redacted-host>), executor path, lockstep oracle on. Driver `tools/model_doom_qwen.py` (host truth machine = upstream `ref.Machine`; ROM `ebreak` breakpoints at frame markers and disk requests; each segment = fresh snapshot + one Qwen turn; the model stops before the store that publishes a disk request and the host executes that store; after each segment the oracle instruction count must equal the truth count (+1) and the model's BYTE tokens must equal the truth console bytes). `tools/model_doom_chunks.py plan|merge` splits a target into token-balanced chunks that can run on different GPUs and merges their results.

| Run | Instr | Chip tokens model/planned | Text tokens | Segments | Model time | Result |
|---|---|---|---|---|---|---|
| probe (`model_probe_qwen.py`) | n/a | 140 | 57 | 1 | seconds | pass, no divergence |
| title-frame (marker 100->101, host prerun 31 s) | 6,563 | 9,999 / 9,988 | 30 | 1 | 55.4 s wall | pass; frame draws nothing, proves tics run |
| boot-frame (cold boot -> first frame marker) | 1,552,382 | 2,091,327 / 2,088,115 | 9,129 | 292 (all ok) | 1,438 s model, 1,460 s wall | pass; 1,454.3 chip tok/s, 1,079.5 instr/s; tok/instr 1.3451 |
Data: TRACES/model/title.json, boot.json, boot.log.gz (per-segment detail in boot.json `segment_detail`).
Tokens per instruction: 1.3451 (boot run), 1.5219 (title, tiny sample), 1.344-1.353 (docstring, planned counts for other targets), 1.4034 (chunkrom dry run), 1.44 (kernel boot via upstream, experiment 03). Use 1.35 for DOOM.
Instr count mismatch across builds: docstring boot-frame 1,552,672 (an earlier ELF) vs run 1,552,382 (run ELF).
Cost model for the next targets (derived, not measured): first level frame 5,842,573 instr, 7,907,244 tokens, 5,151 segments (docstring); at 2.2 k tok/s + 1.7 s/pause that is about 3,600 s + 8,760 s = 3.4 h. The docstring puts a dumped frame at about 750x the cost of the same frame without the dump (time, because of text tokens): a dumped frame is about 4.98 M instr plus 78,115 console bytes, and every console byte is a full-Qwen text token (so the serial dump is not used on the model path). 150 frames at skip15: about 227 M instr, about 305 M tokens, about 38 h of pure token time on one A100 (arithmetic), before pause overhead; chunk ROM removes most pauses.
Result: model executes real kernel+DOOM boot code with zero divergence for 1.55 M instructions. Not done: any E1M1 gameplay frame; any chunk-ROM run; any HF path run.
Chunk driver: written, merge proof (every segment covered exactly once) coded; only dry-run planned.
Key injection: `tools/keysched.py` documents pause points (pc at `qos_key_park`); never run on the model.
