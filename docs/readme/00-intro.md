> ### 🧾 TL;DR
> - 🧠 **What:** a 32-bit RISC-V CPU ([Qwenputer](https://github.com/divagr18/qwenputer)) is built into the layers of Qwen3.5. We wrote a small OS for it and ran the real DOOM engine on top.
> - 🎨 **The model emits the pixels itself:** the model **emits the pixels itself**. The guest dumps each frame as about 32,100 console bytes, every byte comes out of the model as a BYTE token, and every token is checked against a lockstep oracle. The typed flow (`help`, `ls`, `run /bin/doomd`, then frame markers 1-3) is also model-verified ([details](docs/research/TYPED_FLOW_MODEL.md)).
> - 🎯 **Progress:** see the progress line just below. We only count a frame once its model-emitted pixels match the emulator byte for byte.
> - 🐌 **Catch:** slow. One displayed frame took about **18 minutes** of GPU time before (patched driver). With the speed-ups we project about **8 to 10 minutes** per frame (arithmetic, not a measurement). Real time is 0.067 s per frame, so we are still thousands of times too slow.
> - 🔍 **Honest bit:** keys are scripted (or come through the key ring), the clock is virtual, the host serves the disk and collects the bytes into PNGs. Details below.
> - 🕹️ **Play it:** `make live-doom` on the host emulator (not the model). See [boot it yourself](#-watch-it-boot-then-play-it).

<!-- V2:PROGRESS -->
🎯 **All 45 frames were verified through the model. After the optimizations, the clip was retested with the model emitting the pixels too** (byte-exact vs the emulator, zero lockstep divergence; the retest covers 12 of the 45 frames).
<!-- /V2:PROGRESS -->
