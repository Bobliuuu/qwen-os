"""Run model sub-segments of a dumped DOOM frame on Modal (tools/model_fbdump.py split makes the pickles).
  modal run tools/modal_fbdump.py --tag mp1 --ranges 1:5,5:9,...   (one container per A:B range; the model loads once per container)
Volumes: qwenos-q4-rv1 (checkpoint), qwenos-bundle (/mp = tools+ELF+disk), qwenos-mpsnaps (seg<N>.pkl), qwenos-results (<tag>/<A-B>/...)."""
import json, os, shlex, subprocess, sys, time
import modal
HERE = os.path.dirname(os.path.abspath(__file__))
QW = os.environ.get("QOS_QWENPUTER", "/Users/jhome/qwenos-work/out/model/qwenputer_patched/riscv")
image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install("torch==2.14.1", "transformers==5.20.2", "flash-linear-attention==0.6.0", "numpy", "safetensors", "accelerate")
         .add_local_dir(QW, "/opt/qwenputer", copy=True, ignore=["**/__pycache__", "**/.venv", "**/*.pyc"]))
app = modal.App("qwenos-fbdump", image=image)
V = {"/ckpt": modal.Volume.from_name("qwenos-q4-rv1"), "/bundle": modal.Volume.from_name("qwenos-bundle"),
     "/snaps": modal.Volume.from_name("qwenos-mpsnaps"), "/results": modal.Volume.from_name("qwenos-results")}

@app.function(gpu="A100-40GB", volumes=V, timeout=4 * 3600, memory=32768, max_containers=6)
def run(tag: str, rng: str, snapdir: str = "mps"):
    for v in V.values(): v.reload()
    b = "/bundle/mp"; out = f"/results/{tag}/{rng.replace(':', '-')}"; os.makedirs(out, exist_ok=True)
    cmd = [sys.executable, f"{b}/tools/model_doom_qwen.py", "/ckpt/q4-rv1", "--elf", f"{b}/build/qwenos-e1m1.elf",
           "--kernel-elf", f"{b}/build/kernel-doomd.elf", "--disk", f"{b}/E1.img", "--out", f"{out}/console.bin",
           "--result-json", f"{out}/result.json", "--target", "boot-frame", "--segment-range", rng, "--frames", "45",
           "--rom-plan", "build/crx-plan.json", "--sym-elf", "build/doomd-sym.elf", "--load-starts", f"/snaps/{snapdir}", "--k-graph", "64"]
    env = dict(os.environ, PYTHONPATH="/opt/qwenputer", PYTHONUNBUFFERED="1")
    t0 = time.time()
    with open(f"{out}/run.log", "w") as log:
        log.write("CMD " + shlex.join(cmd) + "\n"); log.flush()
        rc = subprocess.run(cmd, cwd=b, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    V["/results"].commit()
    return {"rng": rng, "rc": rc, "wall": round(time.time() - t0)}

@app.local_entrypoint()
def main(tag: str, ranges: str, snapdir: str = "mps"):
    calls = [run.spawn(tag, r, snapdir) for r in ranges.split(",")]
    for c in calls: print(c.get(), flush=True)
