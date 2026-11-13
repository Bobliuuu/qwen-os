```sh
make live-doom                    # fetches engine + Freedoom on first run, boots QwenOS, shell prompt, then type `doom`
make live-doom LIVE_ARGS=--auto   # same, with a typed shell tour
```

<p align="center"><img src="docs/assets/qwenos-live-boot.gif" alt="Recorded live terminal: QwenOS boots, a shell prompt, then DOOM E1M1" width="640"><br><a href="docs/assets/qwenos-live-boot.mp4">MP4</a> · <a href="docs/LIVE_DEMO.md">docs/LIVE_DEMO.md</a></p>

**Honest label: this is tier T0, the host emulator** (`rv32_fast` on your CPU), not the Qwen model. The terminal banner says `tier T0`. On the model a frame took about 18 minutes before the speed-ups and projects to 8-10 with them (see the speed section); the recording is the emulator running the same guest code (kernel, shell, DOOM). Guide, tiers and the model path (T2): [`docs/LIVE_DEMO.md`](docs/LIVE_DEMO.md).
