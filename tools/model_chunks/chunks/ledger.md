# Modal production ledger (tag prod1, A100-40GB, list $2.10/h = $0.000583/s)
Cap: Modal workspace allows only 10 concurrent GPU containers total (H100/L40S/A10G tests queued behind them = cap is global, not per type).
c00-c31 -> Modal A100-40GB (results Volume qwenos-results:/prod1/<cNN>/, synced to out/model/chunks/prod1/ every 4 min)
c32-c34 -> RESERVED for the Lambda A100 (Modal volume has placeholder result.json in /prod1/c32..c34 so Modal never runs them; ignore/remove those placeholders when verifying)

## Lambda run of c32-c34
Snapshots (pickled host start state for each segment of the final ELF e3eb1282 / crx-plan af843bac) live in Modal Volume qwenos-snaps as seg<N>.pkl (N = segment index).
Chunks c32,c33,c34 need segments 36:37, 37:38, 38:39 -> seg36.pkl seg37.pkl seg38.pkl (pull the whole volume to be safe, ~100 MB):
  modal volume get qwenos-snaps / ~/crx/snaps/        # from a machine with the modal CLI/profile (Mac), then scp to the Lambda box
On the box (layout ~/crx as made by sync_crx_to_box.sh, but use the Modal bundle copy of tools: out/model/modal_bundle/tools/model_doom_qwen.py has --load-starts):
  cd ~/crx; PYTHONPATH=~/qwenputer/experimental/riscv python tools/model_doom_qwen.py ~/qwenos_model/q4-rv1 --elf build/qwenos-e1m1.elf --kernel-elf build/kernel-doomd.elf --disk E1.img \
    --target boot-frame --segment-range 36:37 --snapshot-marker 0 --frames 45 --rom-plan build/crx-plan.json \
    --split-markers <as in chunks.plan> --split-steps 1708864 --sym-elf build/doomd-sym.elf \
    --load-starts ~/crx/snaps --out out/c32/console.bin --result-json out/c32/result.json
(exact extra args = the line for c32/c33/c34 in chunks.plan; only --segment-range differs; --load-starts skips the host replay, otherwise each chunk replays ~80M instr in Python.)

## 22:55 change: lockstep hot-spot fix
py-spy: 74% of main-thread time in chipformer/rv/chat.py:365 `expect.pop(0)` (O(n) list pop on a multi-million-token list, quadratic). One core pinned, GPU 15%.
Patched copy (list -> collections.deque, popleft; behavior identical) at out/model/qwenputer_patched/riscv, used via QOS_QWENPUTER.
- c00-c10: old code (running as prod1, A100)
- c11-c31: re-submitted as tag prod1p with the patched copy (placeholder result.json in prod1/c11..c31 so queued old-code duplicates skip)
- c32-c34: Lambda (placeholder in prod1)
Results dirs: chunks/prod1/ (c00-c10) and chunks/prod1p/ (c11-c31). Merge for model_runverify.

## AWS g5 lane (i-0eb70e13af538209f, A10G) -- c33,c34
c33 done 2026-11-04 04:27Z: 3,476,641 chip tokens, 2.42M instr, 1678 s wall (2072 tok/s), driver with deque-patched chat.py. Results in chunks/c33/.

## 23:40 reassignment of the tail (placeholders in Modal prod1/ and prod1p/ so Modal never runs them)
- c29 (segment 33:34, needs seg33.pkl) -> AWS g5 (after c34)
- c30 (segment 34:35, needs seg34.pkl) -> Lambda A100 (after c31)
- c31 (segment 35:36, needs seg35.pkl) -> Lambda A100 (first)
- c32, c33, c34 -> Lambda / g5 (done / running)
Snapshots: Modal Volume qwenos-snaps /seg<N>.pkl (confirmed present: seg33, seg34, seg35). Segment ranges confirmed from chunks.plan.
c34 done: "model_chip_tokens": 1575918, "wall_seconds": 775.0. Results in chunks/c34/. c29 queued next on same box.
c29 done on AWS g5: "model_chip_tokens": 3660576, "wall_seconds": 1755.7. Results in chunks/c29/.
