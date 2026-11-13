| Term | Meaning |
|---|---|
| 🎲 **tic** | One step of DOOM's game logic. DOOM runs 35 tics per second. |
| 🖼️ **frame** | One picture we actually draw. The clip draws 15 frames for every 35 tics (about 15 fps). |
| 🧱 **chunk** | One separate model run covering a slice of the trace. The clip is 35 chunks stitched together, each started from a host snapshot. |
| 🔒 **lockstep** | The model executes each instruction while an oracle (a trusted reference) executes the same one. Any mismatch is a divergence. We saw zero. |
| 🔤 **chip token** | A token the model generates as part of executing one guest instruction. About 1.345 per instruction. |
| 🟦🟨🟩 **T0 / T1 / T2** | Who ran the code. T0: the C emulator and our Python reference. T1: the upstream reference CPU, the oracle, checked against T0. T2: the real Qwen model with a lockstep oracle. |
| 🔤 **BYTE token** | The model emitting one console byte as text. Every pixel byte of a frame comes out this way. |
| 🧩 **segment** | A stretch of a model run between host interventions such as disk service. |
| 📀 **chunk ROM** | Game data served from a read-only ROM window, which cut disk requests from 165,054 to 4. |
