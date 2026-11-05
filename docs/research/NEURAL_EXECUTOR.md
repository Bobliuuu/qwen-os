# Speeding up RISC-V execution inside the Qwenputer (single stream)

Scope: how the guest RV32IM program becomes chip tokens, where the A100 time goes, what an in-weight superinstruction would need, what could be built and tested on a CPU, and which GPU experiments to run once spend is approved. Nothing here was run on a GPU. Every number is tagged **measured** (from a retained result file or a CPU run done for this note), **arithmetic** (derived from measured numbers) or **inference** (a hypothesis the proposed experiments would test).

Sources read: this repo (`tools/model_doom_qwen.py`, `docs/research/experiments/20-model-runs-a100.md`, `HONESTY.md`, `MERGE_NOTES.md`), the per-chunk `result.json` files and `chunks/ledger.md` under `/Users/jhome/qwenos-work/out/model/`, and a shallow clone of `divagr18/qwenputer` (main, cloned 2026-11-04) at `experimental/riscv/chipformer/{rv,q35}`. Paths prefixed `up:` are upstream, relative to `experimental/riscv/chipformer/`. The patched copy `out/model/qwenputer_patched/riscv` differs from upstream in one file, `rv/chat.py` (list to deque for the lockstep queue). The "Locals" inference engine could not be found by web search (no source matched), so nothing below relies on it; as the task notes, an aggregate-throughput claim says nothing about single-stream RISC-V speed.

## Headline findings

1. The 1,100 instr/s on the README is a mixture. **Measured** per-chunk rates on A100 (ledger, 18 chunks run with the patched driver): median 2,408 chip tok/s, 1,679 instr/s aggregate (range 2,104 to 2,581 tok/s). Chunks run with the original driver: 672 instr/s aggregate (634 to 1,600 tok/s). The original driver spent 74% of main-thread time in `expect.pop(0)` on a multi-million-element list (ledger, py-spy), with the GPU about 15% busy. The cold-boot run (1,079 instr/s) is a third regime: 292 segments and 9,129 text tokens.
2. The executor path (CUDA graph per token) is already used, and the lockstep oracle is a minor cost (about 1 to 2%, arithmetic). What remains is a per-token host loop. Rates on three different GPUs (A100 2.4k, A10G 2.07k, L4 3.2k per upstream docs) do not track GPU speed, which points to host/launch latency rather than GPU compute (**inference**; experiment E1 settles it).
3. In-weight fusion saves tokens only where an intermediate result is dead, and on the real DOOM trace the best simple candidates cover 2% (lui+addi) to 5% (add+load) of tokens, at the price of recompiling the circuit and re-merging and re-verifying the whole checkpoint. Not a good first move.
4. Guest-side and driver-side changes need no circuit change and look more valuable: removing the host sync per token and batching K tokens per CUDA graph (E1/E3), and cheaper value records (section 3.5).

## 1. How one guest instruction becomes chip tokens

### 1.1 There are no fetch/decode tokens

The trace is "one record per instruction"; machine state changes only at a record's last token; "the PC is implied: PC = ROM_BASE + 4 * (anchor + n)" (`up:rv/spec.py:1-6`). The tokens are results, not micro-steps. Fetch, decode and execute all happen inside the single forward pass of the chip layers at one token position. Each position computes the instruction the *next* token belongs to: "the state it reads is the state after the position's own commit, so at a record's last token the circuit already works on the next instruction, and inside a record it recomputes the current one" (`up:rv/core.py:3-6`).

Record shapes (`up:rv/spec.py:44-62`, `up:rv/ref.py:445-548`):

| instruction | tokens |
|---|---|
| rd-writing ALU, load, LUI, AUIPC, MUL | `F0` (value fits signed 15 bits) / `V F1` (fits 30 bits) / `V V F2`, from `value_record` (`spec.py:120-129`) |
| DIV/REM | `QS`, up to 8 `QD`, then the value record (up to 10+ tokens) |
| SW | `ST0`/`ST1` (1 token, data not in the stream) |
| SB/SH | `V V V SS0/SS1` (4 tokens, merged word) |
| not-taken branch, rd=x0 op, FENCE | `NT` |
| taken branch, JAL, JALR | `J(target word)`, link written in-circuit |
| every 63 sequential instructions | one extra `R` refresh token |

Why values take up to 3 tokens: a token's output code is a family id plus a 16-bit payload (`core.py:57-58`, `NPAY = 16`), so a 32-bit value needs up to three 15-bit chunks.

### 1.2 The chip layers (`up:rv/core.py:8-37` module doc, build at `core.py:299-1170`)

| layers | work | lines |
|---|---|---|
| L1 | PC head (anchor), counters `count` (2^-n), `j`, `vcnt`, thermometers | 311-346 |
| L2 | PC word w = anchor+n, link word w+1, DIV digit count | 348-380 |
| L3-4 | ROM fetch: two attention sublayers, 16 key heads x 2 value heads each, a 64K-word table of pre-decoded 4-byte words (`rom_word`, `ref.py:344`); MLP decodes uop/register one-hots | 382-442 |
| L5 | register file as DeltaNet tables, three read ports (RS1, RS2, RD); adder stage 1, logic, shifter, multiplier stage 1 | 444-507 |
| L6 | adder stage 2, shifter/multiplier stage 2, DIV products | 561-700 |
| L7-8 | RAM (32 KB, two attention sublayers), loads, SB/SH merge, compares, branch and Zba target adders | 816-856 |
| L9 | DROM (128 KB read-only bytes), multiplier stage 5 | 857-882 |
| L10 | DIV compare signs, rd value select (`srcs`, `core.py:1003`) | 995-1055 |
| L11 | output code: the `case(...)` list picks family and payload bits (`core.py:1065-1130`) | 1055-1170 |

Standalone circuit build on CPU for this note (**measured**, `core.build(core.T4B, None)`, 3.9 s): 18 sublayers (8 attention, 10 MLP), 2,679 dims, 42,014 MLP units, 191 value heads. The merged checkpoint (`TRACES/model/merge.log`) reports 11 chip layers, 2,918 dims, 103 heads, 42,114 units, busiest layer 8,149 of 9,216 MLP units and 16 of 16 key heads, slots 1,265, hidden 3,968.

### 1.3 DeltaNet state versus KV

All chip state lives in Gated DeltaNet value-head matrices, never in a KV cache. In the Triton executor each value head is a `[128,128]` fp32 matrix `S` plus a 3-deep lag history of the residual (`up:rv/tritonexec.py:173-270`, `st["S"]`, `st["hist"]`). Tables: PC anchor, counters, register file (three copies, one per read port), quotient digits, ROM, DROM, RAM, digit file. A table write is one row per head per step (`tl.store(Sb + krow*128 ...)`, `tritonexec.py:133`); decay is only 1 or 0.5 (`tritonexec.py:126`). `snapshot()` (`core.py:1218`) fills these from a host machine state. Chip tokens never touch Qwen's 32 text layers or their KV cache; only text tokens (console echo, the GO turn) do (`up:rv/chat.py:394-420`).

### 1.4 Tokens per instruction on the real trace

**Measured** (CPU, this note, `tools/neural_trace_profile.py`, upstream `ref.Machine` on `qwenos-e1m1.elf`, instructions 3.42M to 4.92M of the cold boot after level load, disk served by the host mailbox): 1,496,107 instructions, 2,129,077 tokens, **1.4231 tok/instr**, 3,893 R refreshes. Record lengths: 1 token 1,034,504; 2 tokens 350,423; 3 tokens 58,668; 4 tokens (SB/SH) 51,341; the rest are DIV records (up to 10). Extra tokens beyond one per record are 29.6% of all tokens. This agrees with the 1.43-1.44 measured on the chunk runs; the 1.345 in the docs is the boot window.

Two-token records by value range (same window): 121,063 are >= 0x80000, 99,749 are 0x20000..0x7ffff (ROM/DROM addresses), 65,824 are 0x4000..0x7fff (upper half of the 32 KB RAM), 33,617 are 0x8000..0x1ffff, 30,034 negative below -16384; 3-token records: 58,212.

Share of tokens by op: LW 15.7%, ADD 13.7%, ADDI 12.7%, SB 7.6% (4 tokens each), SLLI 5.7%, SRLI 5.3%, SW 5.3%, LBU 3.7%, MUL 2.8%.

### 1.5 Where per-token time goes

Per token the driver (`up:rv/chat.py:324-432`) does, in Python:

1. lockstep compare (`expect.popleft()`, line 365 in the patched copy) and the QwenOS `on_token` callback (`tools/model_doom_qwen.py:414-424`);
2. `_exec_step` (`chat.py:92-96`): embedding row lookup (`torch.stack` of cached rows), `xbuf.copy_`, `graph.replay()`, a kept-dim copy;
3. `code_token` (`chat.py:172-185`): `bool((code != 0).any())` and `.tolist()`, two device-to-host syncs per token, then Python bit decoding.

Inside the graph: `Executor2.step` (`tritonexec.py:272-290`) launches per sublayer one kernel plus one `_apply_kernel`: 18 sublayers x 2 = **36 kernels per token** (arithmetic from the standalone build). MLP kernels use sparse CSR rows with atomic adds; head kernels run one program per value head with `tl.debug_barrier()` and an `argmax`-driven read of at most `QHOT` rows.

The lockstep oracle: `bridge.Session.qwen` runs the Python reference to HALT in one call before the segment's tokens are compared (`chat.py:380-385`). The host reference ran 4.92M instructions in 35 s in the profiling run above (about 140k instr/s, **measured**), so a 2.5M-instruction chunk pays about 18 s of a roughly 1,600 s run: **1 to 2%** (arithmetic). It is inside `model_seconds` (`model_doom_qwen.py:438`) but not a bottleneck, except in the original driver where the quadratic `pop(0)` made it one.

Text tokens: full Qwen at 62-68 ms each at batch 1 on an L4 per upstream (`up: docs/rv32.md`, "Speed (L4)"); an A100 figure was never measured here. Each segment emits about 30 text tokens (single-segment chunks show 30-31 in `result.json`). The 292-segment boot run has 9,129 text tokens: at 65 ms that is about 590 s of its 1,438 s (arithmetic using the L4 figure, so an estimate).

## 2. The A100 bottleneck

### 2.1 What the numbers say

| run | source | tok/s | instr/s | note |
|---|---|---|---|---|
| boot-frame, 292 segments | `TRACES/model/boot.json` | 1,454 | 1,079 | 9,129 text tokens, 292 snapshot/turn setups |
| prod1 chunks (original driver) | `out/model/chunks/prod1/*/result.json` (14) | 960 | 672 | quadratic lockstep queue |
| prod1p chunks (patched driver) | `chunks/prod1p/*/result.json` (18) | 2,415 (median 2,408) | 1,679 | 1-2 segments each |
| A10G chunk c33 (patched) | `chunks/ledger.md` | 2,072 | about 1,440 | |
| L4, upstream docs | `up: docs/rv32.md` | 3,200 | n/a | chip tokens only, calc workload |

The README/HONESTY "about 1.1 k instr/s" is therefore the boot run (and the all-chunk average of 1,051 instr/s on A100-40GB, which mixes in the slow old-driver chunks). For long chunk-ROM segments with the patched driver the measured rate is about 1.6-1.8k instr/s, 415 us per chip token.

### 2.2 Plausible bottleneck (inference)

- The three GPUs differ in speed (A100 is the fastest) but not in rate; the rate is closer to a host-side per-token cost. Candidates in the loop: two syncs and several tiny launches per token, 36 kernel nodes per graph replay with data-dependent sparse gathers and atomics, Python callbacks.
- A pure GPU floor can be estimated only by measurement: E1 replays the same graph back to back without a host sync and reports microseconds per token.
- If the floor is far below 415 us, a device-resident decode loop (section 2.4) is worth a large factor; if it is near 415 us, only kernel work or fewer tokens help.

### 2.3 Is `executor=True` used? Yes.

`tools/model_doom_qwen.py:374-375` builds `RvChat(..., fast=not args.no_executor, executor=(torch.cuda.is_available() and not args.no_executor))`, and `experiment 20` / `result.json` record `executor: true`. This is upstream's "Executor v2: the circuit's step as fused Triton kernels ... under one CUDA graph" (`up:rv/tritonexec.py:1-17`). It is not "verify" mode (which would run the HF chip path beside it and be slower).

### 2.4 What upstream's specialized path does that QwenOS does not use

- Batched rows: `Executor2(c, batch)` takes B rows (`tritonexec.py:173`), and `rvbatch.py` batches text tokens of up to B conversations. Chip bursts of different rows still run one after another ("a batched executor is the next speedup", `docs/rv32.md`). Single-stream guest execution cannot use rows from other streams, but a fleet of independent chunks could (E5), which raises aggregate throughput only.
- QwenOS keeps one CUDA graph per *token* and a host loop around it. Nothing upstream or here captures several tokens per graph or keeps the sampler on the device. Chip-token inputs depend only on the previous token's code bits, and the embedding of a chip token is a small function of its id, so both could live on the GPU.
- Text path: upstream measured with torch's linear-attention fallback and the reference `causal_conv1d` (no fla installed); the Modal image installs `flash-linear-attention`, the other boxes may not. This affects only the roughly 30 text tokens per segment.
- Lockstep verification is done on the host in Python. The expected token list could be uploaded and compared on the device in bulk.

### 2.5 Design that needs no circuit change: K tokens per graph (verification mode)

Teacher-forced chunk verification feeds the reference tokens, so the inputs are known in advance (the oracle already computed them: `lock.toks`). Stage K embedding rows, capture K executor bodies in one CUDA graph, replay once, copy K kept-code rows back, compare them with the K expected tokens in one go. Per group: one launch instead of K, one sync instead of 2K. State rollback is unnecessary because on a mismatch the run aborts anyway; at the end of a segment the stream stops at HALT with a partial group handled by a single-token graph. This preserves every claim in `HONESTY.md` (the model still predicts every token and each is compared) because the prediction compared is the model's own output code at that position given the true prefix. `tools/exec_microbench.py` mode C measures this ceiling. Caveat: the autoregressive generation mode (the model's own token fed back) is stricter than teacher forcing, but with a lockstep oracle that stops at the first difference the two are equivalent up to that point, which is also how the current driver treats it.

## 3. In-weight superinstructions: feasibility

### 3.1 What a superinstruction has to change

To retire two instructions per token position:

1. fetch two words (w and w+1) at one position;
2. execute the second on the first's result (forwarding), or fuse statically;
3. commit one or two register writes and advance the PC by 2, and
4. emit a record whose tokens still let the lockstep check mean something.

### 3.2 Hard limits found in the code

| limit | evidence | consequence |
|---|---|---|
| Only the PC step is hard-wired to 1 per final token | `core.py:316` `c.counter("count", isJR, c.final - isJR)`; the counter head decays by 0.5 per step (`core.py:229` `a = 110*step + 238*reset`, executor `fac` at `tritonexec.py:126`) | n += 2 is not expressible in this counter. Skip by emitting a `J` (anchor = w+2, n = 0) instead, which already works (`core.py:1087`, `ref.py:469`) |
| One ROM read per position, 32 key heads fully used | L3-4: 16 key heads x 2 sublayers, 16 of 16 key heads in the busiest layers (`merge.log` `max_heads 16`) | A second ROM read of w+1 needs a duplicate table in two more attention sublayers (more layers, 256 KB of extra state per snapshot) |
| One write per head per step | one row store per value head (`tritonexec.py:133`) | Two live register writes at one commit need two write ports and a rule for which copy is current. Dead-intermediate fusion needs only one write |
| Value of the second instruction is computed only after L10 | rd value select at L10, output at L11 (`core.py:995-1055`) | A dependent second ALU op needs a second adder stage chain after L10 (at least 2 more MLP levels), so more layers |
| MLP capacity of the busiest layer | `max_units 8149 / 9216` (`merge.log`) | New decode work goes into new layers, not into the busy ones. Total unit use is only 42,114 of about 101k, heads 103 of 176 slots, so dims and total capacity are not the wall |
| ROM word is 32 bits | uop 7 + RD 5 + RS1 5 + RS2 5 + 10 spare (`ref.py` module doc, `rom_word`) | A fused word can hold at most a 20-bit constant (as LUI's upper field does), not two full instructions |
| Token payload is 16 bits | `core.py:58` | A fused record cannot carry two 32-bit results; either one result (dead intermediate) or the values must be hidden in the circuit (like a JAL link) |
| 32-bit memory bus | RAM reads are 32-bit words, sub-word merge at L7-8 | A fused load+op can use at most one memory access; two loads in one position would need two RAM reads (two more attention sublayers pairs) |

Hidden size 3,968 is a merge parameter (Qwen dims plus 1,265 chip slots, `merge.log`), not a wall for the *chip* design, but widening it makes every GEMM of the 32 text layers wider and so slows text tokens.

### 3.3 Verdict

Feasible as a circuit change; infeasible as a weights-only edit of the shipped checkpoint. The circuit is compiled, not trained (`core.build` emits weights from a graph), so "retraining" is not the cost. The cost is: change `core.py` (new uop, decode terms, new `jl` sources and a `case`), extend `ref.py`/`spec.py`, rebuild with `python -m chipformer.rv.merge BASE --out DIR` (a 31 GB-RAM CPU job per `docs/rv32.md`), re-run upstream's replay/lockstep checks and invalidate the existing chunk ledger (those 35 chunks verified the old circuit). I estimate days of engineering, mostly verification, not GPU dollars (**inference**).

### 3.4 Smallest concrete fusion: LIJ (lui+addi / auipc+addi into one J token)

```
lui  rd, hi20            LIJ rd, imm20      (rd != x0, c = hi20<<12 + lo12 fits signed 20 bits)
addi rd, rd, lo12   =>   record: J(w+2)     instructions retired: 2, tokens: 1
```

Why this one: it needs no second ROM read (the constant is folded on the host, which already writes the ROM at snapshot time), no second register write (rd1 == rd2, the first result is dead), no new ALU path (the value is a constant) and no change to the PC counter (a `J` resets anchor and n). Every ROM/DROM/RAM address fits 20 signed bits (< 2^19).

Circuit changes needed:

1. ROM word: uop `LIJ` with RD = rd and the 20-bit constant in RS1 (bits 0-4), RS2 (5-9) and S0..S9 (10-19), the same field LUI already uses (`core.py:437` `upper = RS1b + RS2b + spare[0:10]`). Layout verified bit-exact by `tools/neural_fuse.py` (`lij_rom_word`, `lij_fields`).
2. Value path: extend `jl[i]` (`core.py:433`, the "link, computed at t-1" source that already feeds register writes through `Chan(jl[i], (0,1,0,0))`, `core.py:459-460`) with a term `uop_terms("LIJ", [const_bit_i])` (sign-extended). `reg_beta` already includes the `J` family (`core.py:462`).
3. Next token: `case(nr + [uops["LIJ"]], "J", w2)` with `w2 = add_small(anchor, 2, 16, "w+2")`, next to the JAL case (`core.py:1087`); `valc` unchanged (LIJ is not a value-record op).
4. Host: peephole that rewrites ROM position w (leaving w+1 as the original addi so a branch into w+1 behaves as before) and the instruction counter in the driver (`oracle.steps` counts 2 for LIJ; `model_doom_qwen.py:441` compares `oracle.steps - start == instr + 1`, so the planner's instruction count must use the fused count).
5. Cost in layers: none expected (reuses L2 w-arithmetic, L3-4 ROM, L5 register write). One extra `add_small` (about 20 MLP units per bit); it should not enlarge the 18-sublayer depth, but that must be confirmed by a rebuild.

Effect on the real trace (**measured**, same CPU window as 1.4; `rep["fusion_candidates"]` in the profile JSON). Counting only pairs with rd1 == rd2 (provably dead):

| fusion | pairs | share of instr covered | tokens saved if the fused record is one `J` | share of all tokens |
|---|---|---|---|---|
| lui+addi (li32; LIJ requires the result to fit 20 bits, which is a subset) | 14,164 | 1.9% | 42,132 | 2.0% |
| add/addi/slli then load, load overwrites the register (dead) | 62,162 | 8.3% | 115,521 | 5.4% |
| slli(1..3)+add into sh{1,2,3}add (dead) | 4,333 | 0.6% | 5,451 | 0.3% |
| mul+add/shift (fixed point) | 8,759 | 1.2% | 19,237 | 0.9% |
| auipc+addi, addi+addi | 0 and 11 | 0% | about 0 | 0% |

Upper bound for LIJ alone: 2.0% fewer tokens, and 14,164 of 1.5M forward-pass positions (0.9%) removed. An address-arith+load fusion (`LDX`) would have to add a register+register effective address (`A+B`, the adder has 4 operand modes but loads use A+imm), hide the loaded value in a `J` record like a link, and carry ~5.4%. Neither moves the needle by much compared with section 2.5. Pairs where both results are live (e.g. LW+ADDI) gain no tokens at all, since each live result still needs one token.

Honesty cost of any hidden-value record: a `J` record carries no value token, so the loaded or computed value is no longer in the stream and lockstep detects an error in it only when it later reaches a branch, a load of stored data, or the console. This weakens "every instruction result is a token checked against the reference". The shipped trace already behaves this way for SW data and JAL links, so it is a degree, not a new kind, but `HONESTY.md` would need a sentence.

### 3.5 Bigger lever that is also a circuit change: do not emit value tokens

29.6% of tokens (629,077 of 2,129,077) are the second and third tokens of value records. The register write can already come from circuit dims at t-1 (that is how the JAL link works, `core.py:459`); `val[i]` dims exist at L10 for every rd-writing op (`core.py:1004-1028`). A record shape of one `NT`-like token per rd-writing instruction would remove up to about 30% of tokens (arithmetic), simplify the output case list, and cost verification strength as described above (values no longer visible per instruction; a state hash token every N instructions could restore most of it). It also needs recompile, re-merge and a full re-verification. I did not prototype it; it is listed for the owner to decide because it changes what "verified" means.

### 3.6 Guest-side options that need no circuit change

- Zba is already in the circuit (`core.py:816`, `ref.py` `ZBA`) but `ports/doomdmc/build.sh:13` builds with `-march=rv32im`. Compiling with `rv32im_zba` could turn slli+add pairs into `sh{1,2,3}add`. Measured pair frequency is 0.6% of instructions, so the gain is under 1%, with a full rebuild and re-verification of the ELF (the clip's ledger would no longer describe it).
- 3-token and upper-RAM values: 65,824 two-token records in the window carry values 0x4000..0x7fff, i.e. pointers into the upper half of the 32 KB RAM (only values below 16,384 fit in one token). Moving hot pointers/arena below 0x4000 is a link-layout question with large engineering risk (the null-guard finding in `MERGE_NOTES.md` shows layout sensitivity); not recommended without a measured target.
- `-O2` to `-O3`, DIV avoidance: records of 5 or more tokens (DIV, digit ops) are 1,171 of 1.5M records in this window, so no case for DIV work.

## 4. CPU-only prototypes (host-only, labelled as such in their headers)

- `tools/neural_trace_profile.py`: runs upstream `ref.Machine` on a guest ELF and reports tokens per op, record-length histogram, value-range classes of multi-token records and fusion candidates. Output used above. Command (about 35 s): `PYTHONPATH=<qwenputer>/experimental/riscv python3 tools/neural_trace_profile.py --elf <qwenos-e1m1.elf> --kernel-elf <kernel-doomd.elf> --disk E1.img --skip 3420000 --count 1500000 --json out.json`.
- `tools/neural_fuse.py` + `tests/test_neural_fuse.py`: a `FusedMachine` (subclass of the official `ref.Machine`) implementing the LIJ record, the host ROM peephole, and `check_equivalence`, which advances an unmodified machine by the same number of instructions and compares registers, RAM, pc, console and halted after every fused record. **Run**: 7 unit tests pass; `tools/neural_fuse.py --trials 400` ran 400 random programs (3,877 fused records, 23,336 instructions) with zero divergence. The token reduction it prints (27% on the synthetic mix) is for that synthetic generator, not for DOOM. The tests include a branch into the middle of a pair (original addi runs alone), the signed-20-bit boundaries, rd mismatch and x0. This proves the *specification* is consistent; it does not prove the circuit can implement it.
- `tools/exec_microbench.py`: GPU script, **not run, only syntax-checked**; see E1.

## 5. GPU experiments, in priority order (none run; user approval of spend is pending)

Rates used for cost: Modal A100-40GB list $2.10/h (`chunks/ledger.md`), AWS g5.xlarge $1.006/h (`fleet.md`). The Lambda A100 box in memory has no price recorded here; confirm before using. All commands assume `PYTHONPATH=<qwenputer>/experimental/riscv` and the bundle in `out/model/modal_bundle` (ELF `build/qwenos-e1m1.elf`, `build/kernel-doomd.elf`, `E1.img`). Torch with CUDA and triton are required; the 18.7 GB checkpoint is **not** needed for E1-E3.

**E1. Per-token floor of the executor (highest value).** Does the A100 lose its time in the GPU or in the host loop?
```
python3 tools/exec_microbench.py --elf build/qwenos-e1m1.elf --kernel-elf build/kernel-doomd.elf \
  --disk E1.img --tokenizer <Qwen3.5-4B tokenizer.json> --skip 3420000 --tokens 20000 --unroll 16 --profile --json e1.json
```
Metric: us/token for A (graph only), B (host loop as the driver does it) and C (K=16 per graph), plus mismatch counts (exactness) and the top CUDA kernels. Reading: if A is much smaller than 415 us, the host loop is the bottleneck and E3 pays. Cost: about 15 min including circuit build, ROM/DROM snapshot and Triton compile: about $0.5 on Modal A100-40GB. Risk: the script is untested; expect to debug on the first launch (budget a second 15 min, about $1 total).

**E2. Same microbench on other GPUs.** Run E1 on g5.xlarge (A10G) and any L4/H100 available. Metric: whether A scales with GPU memory bandwidth or stays flat (launch-bound). About 15 min each: A10G about $0.30; others at the box's list price (confirm).

**E3. K-token graph in the real driver (verification mode).** Only if E1 shows a large A-versus-B gap. Needs code (stage K rows from `lock.toks`, one sync per K, bulk compare); then re-run one existing chunk to compare with its recorded result. Command is the existing chunk command, for example (from `chunks/ledger.md`):
```
cd ~/crx; PYTHONPATH=~/qwenputer/experimental/riscv python tools/model_doom_qwen.py ~/qwenos_model/q4-rv1 \
  --elf build/qwenos-e1m1.elf --kernel-elf build/kernel-doomd.elf --disk E1.img --target boot-frame \
  --segment-range 36:37 --snapshot-marker 0 --frames 45 --rom-plan build/crx-plan.json \
  --split-markers <as in chunks.plan> --split-steps 1708864 --sym-elf build/doomd-sym.elf \
  --load-starts ~/crx/snaps --out out/c32/console.bin --result-json out/c32/result.json
```
Metric: `chip_tokens_per_s` and `instr_per_s` in `result.json` against the recorded 2.2-2.5k tok/s for the same segment, with zero lockstep error. A 2.5M-instruction chunk takes about 25-28 min today (about $1 on Modal A100); an accelerated run is shorter.

**E4. Text-token cost on A100.** Measure ms per text token and per-segment fixed cost (snapshot build plus the 30-token turn) with the real checkpoint and `flash-linear-attention` installed. Metric: seconds per segment with a one-instruction plan. This decides whether the 292-segment boot run and any many-pause plan are text-dominated. About 20 min with the 18.7 GB load: roughly $0.7 on Modal A100-40GB plus checkpoint staging time.

**E5. Aggregate throughput by batching rows (does not help single-stream).** `Executor2(c, B)` with B independent chunks in one graph, `rvbatch.py` style. Metric: tokens/s per row versus B. Only relevant to wall time for the 35-chunk clip, not to the single-stream goal; run only after E1-E3.

**Not recommended as a GPU experiment now:** an LIJ-capable merged checkpoint. It needs a circuit rebuild first (a CPU job with about 31 GB RAM), then replay/lockstep tests that require a GPU box (about 25 min each for a first 1M-instruction check); decide after E1-E3 whether 2-5% fewer tokens justifies it.

## 6. Recommended order of work

1. E1 (about $0.5): find out whether the A100 is launch-bound.
2. If yes, implement the K-token graph with bulk verification (E3). No circuit change, no new "verified" semantics, keeps the existing ledger valid in kind (the model is still the thing predicting every token).
3. Only then weigh circuit changes: value-less records (up to about 30% fewer tokens) beats LIJ (2.0%) by an order of magnitude, but changes what verification shows.
4. README/HONESTY: replace "1.1 k instr/s end to end" by the measured split (boot run 1.08k; patched long-segment chunks about 1.7k) once the owner accepts the ledger evidence above.
