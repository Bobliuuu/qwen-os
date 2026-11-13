<p align="center"><img src="docs/assets/pixels-arch.svg" alt="Animated pipeline: DOOM engine, LCD dump routine, Qwen chip emitting BYTE tokens, lockstep oracle, host writing the PNG" width="100%"></p>

1. 👾 The **real DOOM engine** (guest RISC-V code in ROM) draws a frame into the guest framebuffer.
2. 📤 A **guest dump routine** (same ROM) writes the frame to the console: about **32,100 bytes** per frame, rows 0-199. The status-bar rows (208-239) are not in a frame's dump.
3. 🧠 The **Qwen3.5-4B chip** executes every one of those instructions inside its weights, and each pixel byte comes out as a **BYTE token**.
4. ✅ The **lockstep oracle** compares every token with a reference CPU. One wrong token would be a divergence. We count zero.
5. 🖥️ The **host** only collects the bytes, applies the palette and writes the PNG.

**What is a BYTE token?** The model normally generates "chip tokens" that carry out an instruction. When the guest writes a byte to the console, the model emits that byte itself as a special BYTE token. So a pixel is literally generated text.

**Why were the first clip's pixels read by the emulator?** Dumping a frame is extra work for the model (about 32,100 more bytes per frame), so for the first 3 s clip we had the emulator read the frame out of guest memory and spent the model's time verifying the instruction trace. The research notes list an early serial pixel dump (78 k tokens per frame) among the dead ends for the same reason. After the optimizations below, we retested the clip with the model paying that cost too: it emits every pixel byte itself.

**Retest on the optimized build, model-decoded pixels (MP4 plays at 15 fps, the GIF is slowed to 4 fps):** [MP4](docs/assets/qwenos-doom-modelpixels.mp4)

<p align="center"><img src="docs/assets/qwenos-doom-modelpixels.gif" alt="DOOM frames from the retest, every pixel byte emitted by the Qwen model" width="480"></p>


---
