# Combined build (perf/combined): GPU benchmark bundle

Branch `perf/combined` of Bobliuuu/qwen-os = perf/compiler + perf/hotloops + perf/sim (+ bbtrace tooling), with engine patches
dmc100-qwenos-merged then dmc100-hotloops on DMC100-Doom 0cdc78e. Host-emulator (rv32_fast) numbers only; nothing here ran on the model.

Layout (same as ~/crx on the GPU boxes, see out/model/sync_crx_to_box.sh):

    build/qwenos-e1m1.elf   combined image  md5 1a718be00a5215441acadddaada14640
    build/doomd-sym.elf     engine symbols (q_stop_at)  md5 159eac06af9792c52e72731c62537c8f
    build/kernel-doomd.elf  kernel (unchanged)  md5 93bd57bbed5eeda46cc7f68e96986c95
    build/crx-plan.json/.bin chunk-ROM plan (.bin md5 af843bac13f2cbab6eb2409748209c5d, identical to the published plan)
    E1.img                  disk image  md5 6287a13cc1079b697e1885f8f6327e06 (same as the published clip)
    chunks.plan             17-chunk plan (>= 4.7M tokens per chunk) for the 45-frame clip
    chunks35.plan           35-chunk plan (like the published one); runplan_clip3s_combined{,_35}/runplan.json + commands.txt
    old/                    the published clip bundle (e3eb1282... ELF, its plan, E1.img, runplan_clip3s.json) for A/B

(the top-level qwenos-e1m1.elf, crx-plan.*, doomd-sym.elf, kernel-doomd.elf are copies of build/*)

Clip (45 drawn frames, game tic 102): combined 72,277,308 instr / 100,537,735 planned chip tokens (tok/instr 1.391 planning model)
vs published 81,065,587 instr / 112,762,231 tokens: -10.8 % instr. In-run disk requests: 2 (level load, chunk 0); the rest is served by the ROM windows.

## Run ONE chunk (c00 = boot to first frame, segments 1:4 of chunks35.plan; 3,111,016 instr, 4,327,423 planned tokens)

On the GPU box (venv, ~/q4-rv1 merged model, PYTHONPATH=~/qwenputer/experimental/riscv, tools/ from the repo: model_doom_qwen.py chunkrom.py
upstream_ref.py upstream_doomd.py wad_device.py rv32_qwenputer.py):

    # COMBINED (cd to the directory holding build/ and E1.img of this bundle)
    SPLIT=$(sed -n 2p chunks35.plan | sed 's/.*--split-markers \([0-9,]*\).*/\1/')
    CUDA_VISIBLE_DEVICES=0 python tools/model_doom_qwen.py ~/q4-rv1 --elf build/qwenos-e1m1.elf --kernel-elf build/kernel-doomd.elf \
      --disk E1.img --target boot-frame --segment-range 1:4 --out out/comb_c00.bin --result-json out/comb_c00.json \
      --snapshot-marker 0 --frames 45 --rom-plan build/crx-plan.json --sym-elf build/doomd-sym.elf --split-markers $SPLIT

    # OLD: cd old/ and run the same command with its own build/, E1.img and the c00 line of out/model/chunks.plan
    # (that line adds --split-steps 1708864 and its own split-markers; use it verbatim)

Or use the fleet runner unchanged: `NGPU=1 ./run_chunks_crx.sh chunks35.plan` (put build/, E1.img, chunks35.plan in ~/crx).
No GPU: add `--dry-run` (reference machine stands in; not a model result).

## Host-emulator reference state of the first ~3M-instruction segment

rv32_fast with the chunk-ROM plan (CRXPLAN=build/crx-plan.bin CRXBASE=29000, E1.img above, mailboxes 154 15c):

| stop after | RAM dump md5 (32 KiB .ram) | console md5 |
|---|---|---|
| 3,000,000 steps | 6eb995b6205da4ad5bb5c5adf1a9c6e9 | 49511d4dc8fb08495b77e7295ff767e6 |
| 3,111,016 steps (end of c00) | 4125890504e0782541c8d0d45a381df1 | 49511d4dc8fb08495b77e7295ff767e6 |

RAM = emulator memory image (registers not included). The driver's own lockstep check against the reference machine is the authority for a chunk.
