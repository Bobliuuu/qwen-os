# 02 Real-WAD BSP viewer on Freedoom (v0.12)

Goal: render a real map from a real IWAD (Freedoom 0.13.0 `freedoom1.wad`, E1M1) in the 32 KiB budget before attempting an engine.

Method: `/bin/doom` streams NODES/SSECTORS/SEGS from the virtual disk, front-to-back BSP traversal, per-column clipping, sector light and sky shading, BLOCKMAP collision with step/headroom checks. Output 32x24 flat colour.

Numbers (README v0.12, frames in `out/freedoom-e1m1-0*.png`): 225-290 K guest instructions per frame on the reference emulator; 32 tests green.
Result: worked as a map viewer. Not DOOM: no textures, sprites, monsters, doors, tics or sound. Superseded by the engine port; kept as `/bin/doom` in the ROM.
Files: `apps/doom.c`, `ports/doom/hal.{c,h}`, `ports/doom/PORTING.md` (integration contract: host may serve block data only).
Reproduce: needs `freedoom1.wad` (`QOS_FREEDOOM_WAD`); `python3 tools/interactive_frames.py --keys wd` (unverified in this pass).
Evidence: TRACES/frames/01_bsp_viewer_freedoom_e1m1.png.
