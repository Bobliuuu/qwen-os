# 12 RAM squeeze (ram.patch)

Goal: return RAM to the engine so floors can be textured everywhere and larger plans fit.
Applies with `cd repo && patch -p1 < ram.patch`; `make check` green (35 tests). Needs the repacked `ram-E1.img` with the new ELF. Neither is copied here (4 MB and 300 KB; originals in `<WORKDIR>/patches/`): image md5 a617f2cb1dfb74049fa7c5e729af660e, ELF md5 f0c760b733a4bcc0e856a58ee30b9059.

Method and numbers (from `RAM_BUDGET.txt` in the patch):
| Item | v1 | v2 |
|---|---|---|
| kernel core | 0x100..0x5bf, 1,216 B | 0x000..0x097, 152 B |
| disk mailbox | 276 B | 84 B (20 hdr + 64 window; DISK_REQUEST limited to 64 B while doomd runs) |
| framebuffer | 768 B resident | 0 (overlay; FB syscalls stream `FB_COL` packets to the console) |
| stack reserve | 1,408 | 1,152 (measured peak 1,016 B over 12e9 instr) |
| `__frame_start` | 5,760 | 4,448 (-1,312 B) |
| flat cache | 4 x 1,028 B | 1,028 B (88 flats = 90,112 B baked in data ROM) |
| data ROM used | 29.4 KB | 119.8 KB (free 3 KB) |
| record cache | 16 B x 32 sets x 4 | 16 B x 16 sets x 4 |
| E1 map/skill plan mix (27 combos) | 3xA 19xB 1xC 4xD, flat-colour floors | 22xA 5xB, textured everywhere |
Cost: E1M1 DEMO1 frames 400-440: 5.10 M instr/frame (v1, flat colour) vs 5.56 M (v2, textured, w16); the same textured frames with disk flats cost 6.32 M, so ROM flats save 12 %. w8 instead of w16 costs +10 %. Record-cache sweep (sets): 4: 5.38 M, 8: 5.19 M, 16: 5.01 M, 32: 5.25 M (in A/k0 experiments). Plan A arena 9,764 B (v1 3,848 B), plan B arena 15,324 B (v1 9,408 B). Same image/frame: ROM flats vs disk flats pixel-identical.
Agent report: +7.2 KB total RAM gain (consistent with core -1,064 B, stack/frame start shifts and cache cuts; the table gives -1,568 B fixed+stack and -3,084 B flat cache, not independently summed).
Result: worked. Frames: TRACES/frames/04 (flat colour, before) and 05 (textured, after).
Files: `kernel/main.c`, `kernel/start.S`, `linker/{doomd,kernel}.ld`, `include/qos.h`, `tools/{check_layout,merge_elf,doomd_frames}.py`, `tests/test_doomd.py`, `ports/doomdmc/{dmc-ram.patch,mkflatrom.py,mklayout.py,mkimage.sh,RAM_BUDGET.txt,qlcd.c,qplat.c}`.
Reproduce: `make doomdmc-image DMCWORK=<writable DMC copy>`; the image must be repacked (plans/arenas baked into it for this layout).
Dead end inside: RC_LINE 32 (32 B lines) and bigger caches no longer fit E1M7 skill 3 in plan B; see 99.
