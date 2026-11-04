# What is and is not claimed

## Claimed (with evidence)
| Claim | Evidence |
|---|---|
| A genuine DOOM engine (DMC100-Doom, GPL, doomgeneric lineage) builds as an RV32IM application of QwenOS and runs on the C emulator with Freedoom data | out/full/results.txt, goldens, video |
| The merged Qwen3.5-4B checkpoint executed 1,552,382 guest instructions of the real QwenOS+doomd cold boot to the first frame marker, with a lockstep oracle and zero divergence over 292 segments | TRACES/model/boot.json |
| The model executed 6,563 instr of the title loop and passed the probe | TRACES/model/title.json, PROVENANCE 5b |
| Upstream `ref.Machine` boots the QwenOS kernel (120,267 instr) | repo README (no log retained) |

## Not claimed
- "DOOM runs in the model": not true yet. No E1M1 or DEMO1 gameplay frame has been executed by the model. The only model-verified frame marker is the cold-boot picture (title-screen draw from the boot run).
- Real-time or interactive play in the model: the model runs at about 1.1 k instr/s end to end (A100, measured); one game tic costs about 1-5 M instr.
- Any speed number from the upstream README (3.7 k instr/s) as a measured result here.

## Boundaries every demo must disclose (from PROVENANCE section 4)
| Boundary | Detail |
|---|---|
| Disk | The WAD/game data is a host-served block device (256-byte requests, now also writes for saves). It is not stored in the weights. Between model segments the host patches response bytes into the machine state. The host does not parse WADs or run game logic; it serves bytes. With chunk ROM, disk extents are pre-filled into the model's data ROM by the host per chunk. |
| Keys | Keyboard input is simulated and scripted by the host through the input mailbox at step/event boundaries. Debug keys (T teleport, g god mode, x/X exit level, i give all) exist in the video build and are listed. |
| Clock | Virtual (about 1 ms per idle call); game tics are not wall-clock paced. |
| Pixels | Video frames come from the emulator (T0) or reference, rendered from the same state; the model verifies the instruction trace (frame marker, console bytes, instruction count, oracle lockstep), not pixel output. The serial pixel dump is not run on the model (each byte would be a full-model text token). |
| Tiers | Each frame must be labelled T0, T1, or T2. The 1060-frame video is entirely T0, neither T1-lockstepped nor model-verified. |
| Segments | A model run is a series of independent segments, each starting from a host snapshot of the machine state (reference-machine truth state), not one uninterrupted model session; "zero divergence" is per segment against the oracle. |
| Frame rate | Presets: skip 15/35 renders 15 fps while game logic runs every tic; "full" is a 160x200 low-detail view, not 320x200. |
| Map scope | E4M2/M6/M9 are not in the pack, E2M9 and E4M7 exceed the converter's segment limit; "E3 9/9" means packed (8 played in the chain). |

## "DOOM in the model" claim boundary
A fair sentence once gameplay runs on the model: "The merged Qwen3.5 model executed the instruction trace of N frames of DOOM (E1M1, low-detail, skip 15/35) as part of a series of verified segments; pixels were rendered from the emulator state; disk and keys were supplied by the host; clock is virtual." Until then, the fair sentence is the first row under Claimed.

## Inconsistencies found between reports and files
| Item | Reports | Files |
|---|---|---|
| Tokens per instruction | 1.44 (README estimate) | 1.345 (boot.json), 1.35 (docstring); 1.44 comes from the kernel boot, not DOOM |
| Boot-frame instruction count | docstring 1,552,672 | run 1,552,382 (different ELF) |
| First game frame instr | 11.26 M, 6.19 M, 5.84 M, 9.06 M, 3.73 M, 3.91 M | different builds/modes (table in experiment 08) |
| Per-tic cost | 10.47 M -> 3.52 M; 5.14 M; 4.21 M baseline; 1.3 M GAMETICS | different metrics (frame delta vs G_Ticker entry vs dumped video) |
| Test count | README 29, 32; ram.patch 35 | README sections written at different times |
| Skip15 disk requests | 165,054 | lowres batch files 165,061 (maybe a rebuild) |
| Episode counts | E3 9/9 | E3M9 packed, not visited by the chain (episodes.txt) |
| Speed | 3.7 k instr/s | 1.08 k instr/s measured end to end (A100, executor, 292 pauses) |
| Debug-key claim | | video uses T at tic 441 and g at tic 653; tics 2..440 are key-only |
