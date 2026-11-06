# 03 Upstream reference CPU verification

Goal: check that the identical QwenOS ELF runs on Qwenputer's own `chipformer.rv.ref.Machine`, not only on our independent emulator.

Method: `tools/upstream_ref.py build/qwenos.elf --wad-device` uses upstream `chipformer.rv.elf.program` and `ref.Machine`, writing disk replies through the machine's RAM word array (`PYTHONPATH=<qwenputer>/experimental/riscv`). `tools/upstream_probe.py` checks park/resume for the model-probe firmware.

Numbers (repo README, verified 2026-11-03; no raw log was kept): boot exit 0, `QWENOS_BOOT_OK`, 120,267 instructions, about 173 k chip tokens (about 1.44 tokens/instr), probe park/resume passes. Note upstream `generate()` defaults to `max_chip=60000`, so a full boot needs a larger budget on the model path.

Result: worked. Later this reference was used as the "truth machine" for every model run (`tools/model_doom_qwen.py`), and `tools/upstream_doomd.py` checks the doomd ELF against the C twin.

Inconsistency: this 1.44 tokens/instr (kernel boot) is the origin of the "1.44" estimate; the DOOM engine measures 1.345 (boot-frame run) to 1.35 (docstring, other targets). Different code mix; the 1.44 figure should not be used for DOOM budgeting.
Files: `tools/upstream_ref.py`, `tools/upstream_probe.py`, `tools/upstream_doomd.py`, `tools/rv32_qwenputer.py`.
Reproduce: see REPRODUCE.md section "Upstream reference".
