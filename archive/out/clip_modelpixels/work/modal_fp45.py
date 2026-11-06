"""Run whole dumped frames (6 sub-segments each, pkls from fbsplit.py in qwenos-mpsnaps/mine) on the real model, one container per frame.
  FP_MAXC=5 modal run modal_fp45.py --tag fp45 --frames 1,2,20"""
import os, shlex, subprocess, sys, time
import modal
QW = "/Users/jhome/qwenos-work/perf/kern/qp"
MAXC = int(os.environ.get("FP_MAXC", "3"))
image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install("torch==2.14.1", "transformers==5.20.2", "flash-linear-attention==0.6.0", "numpy", "safetensors", "accelerate")
         .add_local_dir(QW, "/opt/qwenputer", copy=True, ignore=["**/__pycache__", "**/.venv", "**/*.pyc", "**/.git"]))
app = modal.App("qwenos-fp45", image=image)
V = {"/ckpt": modal.Volume.from_name("qwenos-q4-rv1"), "/bundle": modal.Volume.from_name("qwenos-bundle"),
     "/snaps": modal.Volume.from_name("qwenos-mpsnaps"), "/results": modal.Volume.from_name("qwenos-results")}

@app.function(gpu="A100-40GB", volumes=V, timeout=3 * 3600, memory=32768, max_containers=MAXC, retries=0)
def run(tag: str, frame: int, parts: int = 6, fast: bool = True):
    for v in V.values(): v.reload()
    b = "/bundle/mp"; rng = f"{frame*100}:{frame*100+parts}"; out = f"/results/{tag}/f{frame}"; os.makedirs(out, exist_ok=True)
    cmd = [sys.executable, f"{b}/tools/model_doom_qwen_fast.py", "/ckpt/q4-rv1", "--elf", f"{b}/build/qwenos-e1m1.elf",
           "--kernel-elf", f"{b}/build/kernel-doomd.elf", "--disk", f"{b}/E1.img", "--out", f"{out}/console.bin",
           "--result-json", f"{out}/result.json", "--target", "boot-frame", "--segment-range", rng, "--frames", "45",
           "--rom-plan", "build/crx-plan.json", "--sym-elf", "build/doomd-sym.elf", "--load-starts", "/snaps/mine", "--k-graph", "64"]
    if fast: cmd.append("--fast-kernels")
    env = dict(os.environ, PYTHONPATH="/opt/qwenputer", PYTHONUNBUFFERED="1")
    t0 = time.time()
    with open(f"{out}/run.log", "w") as log:
        log.write("CMD " + shlex.join(cmd) + "\n"); log.flush()
        rc = subprocess.run(cmd, cwd=b, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    V["/results"].commit()
    return {"frame": frame, "rc": rc, "wall": round(time.time() - t0)}

@app.local_entrypoint()
def main(tag: str, frames: str, fast: bool = True):
    calls = [run.spawn(tag, int(f), 6, fast) for f in frames.split(",")]
    for c in calls: print(c.get(), flush=True)
