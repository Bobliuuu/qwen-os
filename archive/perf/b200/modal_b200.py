"""Modal runner for perf experiments (E1 microbench, E2 other GPUs). Uses same image recipe as modal_chunks.py."""
import os, subprocess, sys, json, time, shlex
import modal
HERE = os.path.dirname(os.path.abspath(__file__))
QW = "/Users/jhome/qwenos-work/out/model/qwenputer_patched/riscv"
WT = "/Users/jhome/qwenos-work/publish/qwen-os/.claude/worktrees/agent-ae9e59d7a7129466e/tools"
image = (modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.14.1", "transformers==5.20.2", "flash-linear-attention==0.6.0", "numpy", "safetensors", "accelerate")
    .add_local_dir(os.environ.get("QOS_QWENPUTER") or QW, "/opt/qwenputer", copy=True, ignore=["**/__pycache__", "**/.venv", "**/*.pyc"]))
app = modal.App("qwenos-b200", image=image)
VOLS = {"/ckpt": modal.Volume.from_name("qwenos-q4-rv1"), "/bundle": modal.Volume.from_name("qwenos-bundle"),
        "/results": modal.Volume.from_name("qwenos-results"), "/snaps": modal.Volume.from_name("qwenos-snaps")}
wt_tools = modal.Mount if False else None
TOOLS_MOUNT = image  # placeholder

def _run(argv, env_extra=None, tag="x"):
    for v in VOLS.values(): v.reload()
    env = dict(os.environ, PYTHONPATH="/opt/qwenputer", PYTHONUNBUFFERED="1", **(env_extra or {}))
    t0 = time.time()
    p = subprocess.run(argv, cwd="/bundle/final", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = p.stdout
    return dict(rc=p.returncode, wall=time.time()-t0, out=out[-30000:])

def mk(gpu):
    def f(argv: list[str], tools_src: dict) -> dict:
        os.makedirs("/tmp/t", exist_ok=True)
        for k, v in tools_src.items(): open(f"/tmp/t/{k}", "w").write(v)
        # upstream_ref etc. from bundle tools
        for fn in os.listdir("/bundle/final/tools"):
            if not os.path.exists(f"/tmp/t/{fn}") and fn.endswith(".py"):
                open(f"/tmp/t/{fn}", "w").write(open(f"/bundle/final/tools/{fn}").read())
        r = _run([sys.executable] + argv)
        if os.path.exists("/tmp/e.json"): r["json"] = open("/tmp/e.json").read()
        return r
    f.__name__ = "perf_" + gpu.replace("-", "_"); f.__qualname__ = f.__name__
    globals()[f.__name__] = f
    fn = app.function(gpu=gpu, volumes=VOLS, timeout=3*3600, memory=32768)(f)
    globals()[f.__name__] = fn
    return fn
FUNCS = {g: mk(g) for g in ("B200",)}

@app.local_entrypoint()
def main(gpu: str = "A100-40GB", script: str = "exec_microbench.py", args: str = "", extra: str = ""):
    src = {s: open(os.path.join(WT, s)).read() for s in ([script] + [x for x in extra.split(",") if x])}
    argv = ["/tmp/t/" + script] + shlex.split(args)
    r = FUNCS[gpu].remote(argv, src)
    print(r["out"]); print("RC", r["rc"], "wall", round(r["wall"]))
    if r.get("json"): print("JSON", r["json"])
