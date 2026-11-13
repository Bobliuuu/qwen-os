You need Clang/LLD, `readelf` and Python 3. No game data is in this repo.

```sh
make check                    # kernel, layout, Python reference CPU, unit tests (no WAD needed)
make demo-elf                 # scripted E1M1 image -> build/demo/qwenos-e1m1.elf (+ chunk-ROM plan)
make live-doom                # THE command: fetches engine+Freedoom on first run, boots QwenOS (T0 emulator), shell, then type `doom`
make live-doom LIVE_ARGS=--auto   # same, but it types a shell tour and `run /bin/doomd` for you
# step by step + real-model (T2, GPU) path: docs/LIVE_DEMO.md
```

`demo-elf` and the live terminal need the engine and a WAD, see [get the engine](#-get-the-engine-and-freedoom). In the live terminal, arrow keys (or w/s/a/d) move, f or space fires, e uses, and `Ctrl-]` quits.
Other handy targets: `CHUNKROM=1 make demo-live` (typed-flow image) and `tools/doomd_regress.sh` (frame and state goldens).
