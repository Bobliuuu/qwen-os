"""Typed-flow model verification on Modal: cold boot -> typed `help`, `ls`, `run /bin/doomd` -> first DOOM frame marker.

Chunks = segment ranges of the typed-flow plan (tools/model_doom_qwen.py --type ... --split-steps ...). Start states come from ONE host
(reference-machine) pass, pickled per segment (--dump-starts) and mounted at /snaps; every chunk then runs the REAL model on its
segment range in lockstep with the oracle.  Run (3 chunks, 3 A100s):
  modal volume put -f qwenos-bundle <bundle dir> /typed ; modal volume put -f qwenos-snaps-typed <snaps dir> /
  QOS_QWENPUTER=<patched riscv dir> modal run tools/modal_typed_chunks.py --tag typed1
"""
import json, os, shlex, subprocess, sys, time
import modal

HERE = os.path.dirname(os.path.abspath(__file__))
QWENPUTER = os.environ.get("QOS_QWENPUTER") or os.path.join(HERE, "..", "..", "qwenputer", "experimental", "riscv")
image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install("torch==2.14.1", "transformers==5.20.2", "flash-linear-attention==0.6.0", "numpy", "safetensors", "accelerate")
         .add_local_dir(QWENPUTER, "/opt/qwenputer", copy=True, ignore=["**/__pycache__", "**/.venv", "**/*.pyc"]))
app = modal.App("qwenos-typed-flow", image=image)
ckpt_vol = modal.Volume.from_name("qwenos-q4-rv1")
bundle_vol = modal.Volume.from_name("qwenos-bundle")
res_vol = modal.Volume.from_name("qwenos-results", create_if_missing=True)
snap_vol = modal.Volume.from_name("qwenos-snaps-typed", create_if_missing=True)
VOLS = {"/ckpt": ckpt_vol, "/bundle": bundle_vol, "/results": res_vol, "/snaps": snap_vol}
TYPED = r"help\nls\nrun /bin/doomd\n"
COMMON = ["--target", "boot-frame", "--snapshot-marker", "0", "--frames", "1", "--rom-plan", "build/live-crx-plan.json",
          "--sym-elf", "build/qwenos-live-e1m1.elf", "--type", TYPED, "--split-steps", "1112000,2224000"]
CHUNKS = {"t0": "1:25", "t1": "25:26", "t2": "26:27"}   # segs 1-24 (boot, 23 typed keys, first 1.24M instr of doomd init), then 2 more pieces to the marker


@app.function(gpu="A100-40GB", volumes=VOLS, timeout=3 * 3600, memory=32768,
              retries=modal.Retries(max_retries=1, initial_delay=5.0, backoff_coefficient=1.0))
def run_chunk(tag: str, name: str, rng: str, extra: list[str]) -> dict:
    for v in (bundle_vol, ckpt_vol, snap_vol):
        v.reload()
    out = f"/results/{tag}/{name}"; os.makedirs(out, exist_ok=True)
    b = "/bundle/typed"
    cmd = [sys.executable, f"{b}/tools/model_doom_qwen.py", "/ckpt/q4-rv1", "--elf", f"{b}/build/qwenos-live-e1m1.elf",
           "--kernel-elf", f"{b}/build/kernel-live.elf", "--disk", f"{b}/E1.img", "--out", f"{out}/console.bin",
           "--result-json", f"{out}/result.json", "--segment-range", rng, "--load-starts", "/snaps"] + COMMON + extra
    env = dict(os.environ, PYTHONPATH="/opt/qwenputer", PYTHONUNBUFFERED="1")
    t0 = time.time()
    with open(f"{out}/run.log", "w") as log:
        log.write("CMD " + shlex.join(cmd) + "\n"); log.flush()
        rc = subprocess.run(cmd, cwd=b, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    res_vol.commit()
    return {"name": name, "rc": rc, "container_wall_s": round(time.time() - t0, 1)}


@app.local_entrypoint()
def main(tag: str = "typed1", only: str = "", extra: str = ""):
    names = [n for n in CHUNKS if not only or n in only.split(",")]
    calls = {n: run_chunk.spawn(tag, n, CHUNKS[n], shlex.split(extra)) for n in names}
    for n, c in calls.items():
        try:
            print(n, c.get(), flush=True)
        except Exception as e:
            print(n, "FAILED", repr(e), flush=True)
