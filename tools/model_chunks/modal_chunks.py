"""QwenOS-DOOM model-verification chunks on Modal GPUs.

Volumes
  qwenos-q4-rv1   merged checkpoint (bf16, 18 GB) at /q4-rv1           (uploaded once)
  qwenos-bundle   <bundle>/{build/*.elf, build/crx-plan.json, E1.img, tools/*.py, chunks.plan}   (swappable)
  qwenos-results  <tag>/<chunk>/{result.json,console.bin,run.log}

Usage (from /Users/jhome/qwenos-work/out/model):
  modal volume put -f qwenos-bundle modal_bundle /final          # stage/refresh the ELF+plan+tools bundle ("final")
  modal run modal_chunks.py --smoke                              # title-frame, 6.5k instr
  modal run modal_chunks.py --bundle final --tag prod1           # all chunks of the bundle's chunks.plan, in parallel
  modal run modal_chunks.py --bundle final --tag prod1 --only c00,c05
  modal volume get qwenos-results prod1 ./prod1                  # download results
Env: QOS_GPU (default A100-40GB), QOS_MAXC (max concurrent containers, default 18).
Finished chunks (result.json present) are skipped, so a re-run resumes.
"""
import json, os, shlex, subprocess, sys, time
import modal

GPU = os.environ.get("QOS_GPU", "A100-40GB")
MAXC = int(os.environ.get("QOS_MAXC", "18"))
HERE = os.path.dirname(os.path.abspath(__file__))
QWENPUTER = os.environ.get("QOS_QWENPUTER") or os.path.join(HERE, "..", "..", "qwenputer", "experimental", "riscv")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.14.1", "transformers==5.20.2", "flash-linear-attention==0.6.0",
                 "numpy", "safetensors", "accelerate")
    .add_local_dir(QWENPUTER, "/opt/qwenputer", copy=True,
                   ignore=["**/__pycache__", "**/.venv", "**/*.pyc"])
)

app = modal.App("qwenos-doom-chunks", image=image)
ckpt_vol = modal.Volume.from_name("qwenos-q4-rv1", create_if_missing=True)
bundle_vol = modal.Volume.from_name("qwenos-bundle", create_if_missing=True)
res_vol = modal.Volume.from_name("qwenos-results", create_if_missing=True)
snap_vol = modal.Volume.from_name("qwenos-snaps", create_if_missing=True)
VOLS = {"/ckpt": ckpt_vol, "/bundle": bundle_vol, "/results": res_vol, "/snaps": snap_vol}


def _run_chunk(bundle: str, tag: str, name: str, argv: list[str]) -> dict:
    """argv = model_doom_qwen.py args after the model/elf/disk/out args (target, --segment-range, extras)."""
    bundle_vol.reload()
    ckpt_vol.reload()
    snap_vol.reload()
    out = f"/results/{tag}/{name}"
    os.makedirs(out, exist_ok=True)
    rj = f"{out}/result.json"
    if os.path.exists(rj):
        return {"name": name, "skipped": True, **json.load(open(rj))}
    b = f"/bundle/{bundle}"
    env = dict(os.environ, PYTHONPATH="/opt/qwenputer", PYTHONUNBUFFERED="1")
    cmd = [sys.executable, f"{b}/tools/model_doom_qwen.py", "/ckpt/q4-rv1",
           "--elf", f"{b}/build/qwenos-e1m1.elf", "--kernel-elf", f"{b}/build/kernel-doomd.elf",
           "--disk", f"{b}/E1.img", "--out", f"{out}/console.bin", "--result-json", rj] + argv
    if "--segment-range" in argv and os.environ.get("QOS_NO_SNAPS") != "1" and "--dump-starts" not in argv:
        cmd += ["--load-starts", "/snaps"]   # host start states pre-dumped by ONE reference pass (see snaps pipeline)
    t0 = time.time()
    with open(f"{out}/run.log", "w") as log:
        log.write("CMD " + shlex.join(cmd) + "\n"); log.flush()
        rc = subprocess.run(cmd, cwd=b, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    wall = time.time() - t0
    res = {"name": name, "rc": rc, "container_wall_s": round(wall, 1)}
    if os.path.exists(rj):
        r = json.load(open(rj)); res.update({k: r.get(k) for k in ("wall_seconds", "model_chip_tokens", "instructions", "lock_error", "head_mismatch")})
        if r.get("wall_seconds"):
            res["chip_tok_per_s"] = round((r.get("model_chip_tokens") or 0) / r["wall_seconds"])
    res_vol.commit()
    if rc != 0:
        raise RuntimeError(f"{name} rc={rc} (see {out}/run.log)")  # triggers retry
    return res



def _wrap(g):
    def f(bundle: str, tag: str, name: str, argv: list[str]) -> dict:
        return _run_chunk(bundle, tag, name, argv)
    f.__name__ = "run_chunk_" + g.replace("-", "_").lower()
    f.__qualname__ = f.__name__
    globals()[f.__name__] = f   # container resolves the function by module attribute
    fn = app.function(gpu=g, volumes=VOLS, timeout=6 * 3600, memory=32768, max_containers=MAXC,
                      retries=modal.Retries(max_retries=2, initial_delay=5.0, backoff_coefficient=1.0))(f)
    globals()[f.__name__] = fn
    return fn


@app.function(cpu=2.0, memory=8192, volumes={"/bundle": bundle_vol, "/snaps": snap_vol}, timeout=4 * 3600)
def dump_starts(bundle: str, first_line: str):
    """ONE host pass over the reference machine; pickles every segment start to the qwenos-snaps volume (committed per segment)."""
    import threading
    b = f"/bundle/{bundle}"
    extra = shlex.split(first_line)
    cmd = [sys.executable, "-u", f"{b}/tools/model_doom_qwen.py", "--dry-run", "--elf", f"{b}/build/qwenos-e1m1.elf",
           "--kernel-elf", f"{b}/build/kernel-doomd.elf", "--disk", f"{b}/E1.img", "--out", "/dev/null", "--target", "boot-frame",
           "--dump-starts", "/tmp/snaps"] + extra
    env = dict(os.environ, PYTHONPATH="/opt/qwenputer", PYTHONUNBUFFERED="1")
    p = subprocess.Popen(cmd, cwd=b, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    import shutil
    for line in p.stdout:
        print(line, end="", flush=True)
        if line.startswith("dumped seg"):
            n = line.split()[2]
            shutil.copy(f"/tmp/snaps/seg{n}.pkl", f"/snaps/.seg{n}.tmp"); os.replace(f"/snaps/.seg{n}.tmp", f"/snaps/seg{n}.pkl")
            snap_vol.commit()
    return p.wait()


FUNCS = {g: _wrap(g) for g in ("A100-40GB", "A100-80GB", "H100", "L40S", "A10G")}


def parse_plan(text):
    chunks = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, target, rng, *extra = shlex.split(line)
        chunks.append((name, ["--target", target, "--segment-range", rng] + extra))
    return chunks


ROM = ["--rom-plan", "build/crx-plan.json", "--sym-elf", "build/doomd-sym.elf"]


@app.local_entrypoint()
def main(smoke: bool = False, bench: int = 0, bundle: str = "final", tag: str = "", only: str = "", plan: str = "",
         gpu: str = "A100-40GB", mix: str = ""):
    """--smoke: title-frame on --gpu.  --bench N: boot-frame capped at N chip tokens on every GPU in --gpu (comma list), in parallel.
    prod: --plan FILE (default bundle plan), --gpu G or --mix 'A100-40GB:20,H100:10' (counts per GPU type, chunks assigned in plan order)."""
    if smoke or bench:
        tag = tag or ("smoke" if smoke else f"bench{bench}")
        argv = (["--target", "title-frame"] if smoke else ["--target", "boot-frame", "--snapshot-marker", "0", "--max-chip", str(bench)]) + ROM
        calls = {g: FUNCS[g].spawn(bundle, tag + "-" + g, "t", argv) for g in gpu.split(",")}
        for g, c in calls.items():
            t = time.time()
            try:
                print(g, json.dumps(c.get(), indent=1))
            except Exception as e:
                print(g, "FAILED", repr(e))
        return
    tag = tag or time.strftime("run%Y%m%d-%H%M")
    text = open(plan).read() if plan else open(os.path.join(HERE, "modal_bundle", "chunks.plan")).read()
    chunks = parse_plan(text)
    if only:
        keep = set(only.split(","))
        chunks = [c for c in chunks if c[0] in keep]
    slots = []
    for part in (mix or f"{gpu}:{len(chunks)}").split(","):
        g, n = part.split(":"); slots += [g] * int(n)
    print(f"{len(chunks)} chunks, bundle={bundle} tag={tag} gpus={dict((g, slots.count(g)) for g in set(slots))}")
    t = time.time()
    if os.environ.get("QOS_DUMP", "1") == "1":
        first = [l for l in text.splitlines() if l.strip() and not l.startswith("#")][0].split(None, 3)[3]
        dc = dump_starts.spawn(bundle, first); print("spawned dump_starts on Modal CPU", flush=True)
    sv = modal.Volume.from_name("qwenos-snaps")
    have = set()
    def refresh():
        nonlocal have
        try:
            have = {e.path.split("/")[-1] for e in sv.listdir("/")}
        except Exception as e:
            print("listdir retry:", repr(e)[:80], flush=True)
    def ready(a):
        ra, rb = (int(x) for x in a[a.index("--segment-range") + 1].split(":"))
        return all(f"seg{k}.pkl" in have for k in range(ra, rb))
    pending = list(enumerate(chunks)); calls = []
    while pending:
        refresh()
        for i, (n, a) in list(pending):
            if ready(a):
                g = slots[min(i, len(slots) - 1)]
                calls.append((n, g, FUNCS[g].spawn(bundle, tag, n, a))); pending.remove((i, (n, a)))
                print(time.strftime("%H:%M:%S"), "spawned", n, g, flush=True)
        if pending:
            time.sleep(30)
    results = []
    for n, g, c in calls:
        try:
            r = c.get(); r["gpu"] = g
        except Exception as e:
            r = {"name": n, "gpu": g, "error": repr(e)}
        print(r, flush=True); results.append(r)
    print(f"done in {time.time()-t:.0f}s; modal volume get qwenos-results {tag} ./{tag}")
    json.dump(results, open(os.path.join(HERE, f"modal_{tag}_summary.json"), "w"), indent=1, default=str)
