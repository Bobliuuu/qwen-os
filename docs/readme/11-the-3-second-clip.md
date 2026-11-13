<p align="center"><img src="docs/assets/qwenos-doom-3s.gif" alt="The 3-second E1M1 clip, 45 frames at 15 fps" width="480"><br><a href="docs/assets/qwenos-doom-3s.mp4">Full-quality MP4 (960x720, 15 fps)</a> · <a href="docs/assets/qwenos-doom-3s-contact.png">contact sheet</a> · <a href="docs/CLIP_LEDGER.md">per-frame and per-chunk ledger</a></p>

> 📝 **Note on this clip:** it was generated with an **older build**. Since then the build got faster: the host emulator runs **-10.8 %** instructions on this clip, and on the real model we measured **2x** from block verification plus fused kernels (chunk c34, see the speed-up table). The optimized build was retested on the model with model-decoded pixels (see above).

E1M1, FULL preset (160x200 low-detail view, status bar), 15 rendered frames per 35 game tics. The player walks forward, turns right, fires the pistol and keeps walking. The input is a compiled-in script (`q_script`), not typed live.

| Field | Value |
|---|---|
| 🎞️ Frames in the clip | 45 (3 s at 15 fps), E1M1 |
| 🧱 Separate model runs stitched | 35 chunks: 29 Modal A100, 3 Lambda A100, 3 AWS A10G |
| ✅ Frames with a model-verified instruction trace | 45 of 45 (real Qwen3.5-based model, lockstep oracle, zero divergence) |
| 🔢 Instructions | 81,065,587 in the run plan; 81,065,591 executed by the model plus 35 host-executed boundary instructions |
| 💽 Disk requests | 4 in total (host-served disk replaced by chunk ROM) |

What "verified" means here: the model executed the instruction trace in lockstep with the oracle, and the frame markers and console bytes matched. **The frames are real output of the real DOOM engine**; the pixel bytes are read from the guest's memory by the emulator (same ELF and state), so Qwen verified the computation that made them, not the pixel values themselves. Disclosures: keys are simulated, the clock is virtual, the disk is host-served through chunk-ROM windows, 35 boundary instructions are host-executed, and each chunk starts from a host-supplied snapshot. Not covered by the clip: the typed flow (a separate run, see above); a full Python-reference replay (only segments 1-4, the C twin covers 5-38); and a +5 instruction difference in chunk c02 that we have not decoded. The original run plan failed instruction-count bookkeeping at the c00-c02 split boundary and was reconciled; the ledger links both.
