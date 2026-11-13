<p align="center"><img src="docs/assets/verified-vs-host.svg" alt="Two columns: what the Qwen model checked in lockstep, and what the host did" width="100%"></p>

| Tier | Who ran it | What it has verified |
|---|---|---|
| 🟦 T0 | C emulator `tools/rv32_fast` and our Python reference | Everything: typed flow, E1M1 gameplay, chunk ROM, regression goldens, a 1060-frame scripted E1M1 video |
| 🟨 T1 | Upstream reference CPU (`chipformer.rv.ref.Machine`), the oracle (see [three ways to run the CPU](#-three-ways-to-run-the-same-cpu-t0-t1-t2)) | Lockstep equal to the emulator for 6,000,000 instr of the merged build (level load and 2 frames); upstream also boots the kernel (120,267 instr) |
| 🟩 T2 | The real Qwen model (merged Qwen3.5-4B, A100) with a lockstep oracle | Probe; title frame (6,563 instr); **cold boot to the first frame marker: 1,552,382 instr, 292 segments, zero divergence**, on an earlier (pre-merge) build |
| 🟩 T2, gameplay | The real Qwen model (Qwen3.5-4B, lockstep oracle) | The 3-second E1M1 clip: 45 frames, 35 chunks, 81,065,587 instr, zero divergence, scripted input (see [the clip](#-the-3-second-clip)). The typed `run /bin/doomd` flow is a separate run, see the next row |
| 🟩 T2, typed flow | The real Qwen model, lockstep oracle | Cold boot, `help`, `ls`, `run /bin/doomd`, first DOOM frame marker and markers 2 and 3: 8,239,190 instr in total, about 11.7 M chip tokens, 27 segments, 4 A100 chunks, zero divergence, every token checked against the oracle. Console through marker 1: 273 bytes byte-identical to the C emulator and the Python reference; through marker 3 the first 315 bytes are identical (the model segment stops at the first not-yet-executed pc after the marker, so it prints 20 extra bytes `DOOMD_FRAME 3 tic 5` and runs about 15k instructions past the emulator's marker). See [TYPED_FLOW_MODEL](docs/research/TYPED_FLOW_MODEL.md) |
| 🟩 T2, pixels | The real Qwen model, lockstep oracle | The guest's LCD dump stream (about 32,100 console bytes per frame, rows 0-199) comes out as model BYTE tokens, each lockstep-checked; the host collects the bytes into PNGs. **retested on the optimized build, byte-exact on rows 0-199; see the progress line at the top** |

Things you should know before you get too excited 🧯:

- 💽 **Disk** is host-served block storage, patched in between model segments. With chunk ROM it is mostly read from the data ROM instead. It is not stored in the weights.
- ⌨️ **Keyboard** input is simulated: the host pushes hardcoded keys through the input mailbox.
- 🕰️ **Clock** is virtual (about 1 ms per idle call), not real time.
- 🖼️ **Pixels**: all frames are genuine DOOM output. In the first clip the pixel bytes were read from guest memory by the emulator and the model verified the instruction trace. Now the model emits the pixel bytes (rows 0-199 only) and the host just collects them. A frame counts as model-decoded only when its bytes match the emulator.
- ⌨️ **Typed-flow run, disclosures** ([details](docs/research/TYPED_FLOW_MODEL.md)):
  - 22 boundary instructions (the park `ret`s) were executed by the host.
  - Keys were delivered at `qos_key_park` through the key ring, one char per park, so each key is present at the same instruction the emulator consumed it.
  - Only `help`, `ls` and `run /bin/doomd` were typed (no cat/echo tour), and no gameplay keys were sent during the frames.
  - The run used the older non-Zba chunk-ROM live ELF (built 2026-11-03), whose shell prints `?` for `help`.
  - The frames' pixels were not checked in that run (marker bytes only); model-decoded pixel frames are a separate run.
- 🧩 **Segments**: a model run is a series of host-snapshotted segments, and "zero divergence" is per segment.
- 🐌 **Not real-time.** See [how fast is it](#-how-fast-is-it-really).
- The clip uses a dedicated E1M1 demo build with scripted input; the typed flow was verified separately. Scope is E1M1.
- Full Python-reference replay covers only segments 1-4; the C twin covers segments 5-38. One chunk (c02) has an unexplained +5 instruction difference that we have not decoded.

Full list: [`docs/research/HONESTY.md`](docs/research/HONESTY.md).
