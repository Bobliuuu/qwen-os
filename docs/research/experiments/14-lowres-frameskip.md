# 14 Low-res and frame-skip presets (lowres.patch)

Goal: find the cheapest configuration that still looks like DOOM, to make a model-run clip affordable.

Knobs (`ports/doomdmc/lowres.sh NAME "flags" [dump]`): `Q_RN/Q_RD` skip pattern (render N of every D tics: 15/35, 1/2, 1/3), `Q_DETAIL=2` (low horizontal detail) with `Q_XTVASH`, `Q_VTOP/Q_VBOT` vertical crop, `Q_NOBAR` status bar off, `Q_FIXEDLIGHT`, `Q_SOLID`, `Q_STRIPW` strip width, `Q_DUMP_COMPACT`, `Q_DUMP_ROW2`. Test route: DEMO1-style 350 tics.

Measured, 350-tic runs on the emulator (TRACES/lowres/lr_batch1.txt, lr_batch2.txt; run without dump unless marked):
| Config | Total instr | Frames | Disk req | GAMETICS mean |
|---|---|---|---|---|
| base (compact dump flag) | 468.2 M | 350 | 309,189 | 1.326 M |
| skip15 (15/35) | 227.0 M | 151 | 165,061 | 0.638 M |
| skip 1/2 | 258.3 M | 176 | 184,365 | 0.721 M |
| skip 1/3 | 185.4 M | 117 | 139,781 | 0.523 M |
| detail 2 | 313.5 M | 350 | 249,041 | 0.886 M |
| crop 160 / crop 120 rows | 432.6 M / 397.1 M | 350 | 305,976 / 300,869 | 1.225 M / 1.124 M |
| no status bar | 458.7 M | 350 | 299,200 | 1.301 M |
| fixed light | 459.6 M | 350 | 309,189 | 1.301 M |
| solid (flat colour) | 443.1 M | 350 | 307,725 | 1.255 M |
| c1 skip15 | 227.1 M (482.9 M with pixel dump) | 151 | 165,061 | |
| c2 skip15 + detail 2 | 160.1 M (292.3 M dump) | 151 | 138,904 | 0.449 M |
| c3 + crop top 60 | 148.0 M (243.2 M dump) | 151 | | |
| c4 + dump row2 | 148.0 M (200.1 M dump) | 151 | | |
| c7 + solid | 143.5 M (195.6 M dump) | 151 | | |
Dump vs no dump on the base: 468.8 M vs 1,599.4 M (b0); compact dump 1,050.0 M.
Presets (agent report, images `TRACES/frames/07,08` and `out/lowres/PRESET_*`): max (80-col cropped, cheapest), balanced, full (160x200 low-detail view with status bar, textured). The 80-column preset looked poor (frames 09 shows the crop); the decision of 2026-11-03 (PROVENANCE 3b) is to use the FULL preset at 15 rendered fps via skip pattern floor(t*15/35), game logic every tic.
Result: worked. Skip 15/35 halves instructions. Serial pixel dump dominates cost (about 3.4x) so model runs do not use it (render pixels from emulator, verify trace).
Dead ends: `Q_STRIPW=16` crashed at start (exit 99 after 298,139 steps in batch1; width 8 identical to base); `Q_NOBAR`, `Q_FIXEDLIGHT` and `Q_SOLID` each gave under 4 %.
Patch: TRACES/patches/lowres.patch (ad8c85ea...; no `diff` headers, plain `---/+++` pairs) plus helper scripts in TRACES/lowres.
