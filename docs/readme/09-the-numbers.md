All from [`docs/research/STATUS.md`](docs/research/STATUS.md), [`MERGE_NOTES.md`](MERGE_NOTES.md) and the [provenance ledger](docs/research/TRACES/PROVENANCE.md). Instruction counts are guest RV32 instructions. "Plain English" is our conversion, using the median 1,679 instr/s where a time is given.

| Thing | Value | Plain English |
|---|---|---|
| 🧠 RAM | 32 KiB (doomd owns 30,800 B while it runs) | 0.03 MiB |
| 📀 Exec ROM / data ROM | 256 KiB / 128 KiB, both read-only | |
| 🔤 Chip tokens per instruction | 1.345 (measured on the model boot) | |
| ⌨️ Typed flow: boot to prompt | 186 instr | about a tenth of a second at 1,679 instr/s |
| 🥾 Cold boot to first E1M1 frame | 2.9 M to 3.7 M instr, depending on build | roughly 30 to 40 minutes at 1,679 instr/s |
| 🎲 Mean instr per game tic, tics 30-300 (FULL preset) | 485,801 with host-served disk, 538,573 with chunk ROM | about 5 minutes per tic |
| 🕐 350 tics of E1M1, total | 180.5 M instr (165,054 disk requests) or 199.7 M with chunk ROM | about 30 hours on one GPU |
| 💽 Disk requests with chunk ROM | **4** in total, 0 inside doomd (down from 165,054) | |
| 📦 Chunk-ROM price | +10.6 % instructions | |
| 🚀 Model speed, A100-SXM4-40GB, end to end (boot run) | 1,454 chip tokens/s, about 1.1 k instr/s | |
| 📚 doomd stack headroom | 960 B used of 1,408 B reserved | |

FULL preset means a 160x200 low-detail view, game logic every tic, and 15 of every 35 tics drawn. Instructions per tic are means over all tics, skipped draws included.
