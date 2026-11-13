#!/usr/bin/env python3
"""Derive docs/derived/readme_data.json (used by README.spec.yml) from the repo's own ledgers:
docs/CLIP_LEDGER.md (per-frame and per-chunk tables), docs/research/typed-flow/*.result.json and
docs/research/TRACES/model/boot.json. Nothing is typed by hand."""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
num = lambda s: int(s.replace(",", "").strip())


def table(lines, start_pat):
    i = next(k for k, l in enumerate(lines) if re.match(start_pat, l))
    rows = []
    for l in lines[i + 2:]:
        if not l.startswith("|"):
            break
        rows.append([c.strip() for c in l.strip().strip("|").split("|")])
    return rows


def main():
    L = open(os.path.join(ROOT, "docs/CLIP_LEDGER.md")).read().split("\n")
    frames = [dict(frame=int(r[0]), tic=int(r[1]), instr=num(r[2]), instr_m=round(num(r[2]) / 1e6, 3), chunks=r[3], lane=r[4], verified=("yes" in r[5]))
              for r in table(L, r"\| frame \|")]
    chunks = []
    for r in table(L, r"\| chunk \| markers"):
        chunks.append(dict(chunk=r[0], instr=num(r[3]), tokens=num(r[4]), lane=r[5].split(" (")[0], wall_s=float(r[6]), ok=r[8].startswith("ok, MODEL")))
    lanes = {}
    for c in chunks:
        x = lanes.setdefault(c["lane"], dict(lane=c["lane"], chunks=0, wall_s=0.0, instr=0))
        x["chunks"] += 1; x["wall_s"] += c["wall_s"]; x["instr"] += c["instr"]
    for x in lanes.values():
        x["wall_h"] = round(x["wall_s"] / 3600, 2); x["label"] = x["lane"]
    typed = []
    for k, name in [("t0", "boot to prompt, help"), ("t1", "ls"), ("t2", "run /bin/doomd, first marker"), ("f3", "frame markers 2 and 3")]:
        d = json.load(open(os.path.join(ROOT, f"docs/research/typed-flow/{k}.result.json")))
        typed.append(dict(step=name, instr_m=round(d["instructions"] / 1e6, 3), instr=d["instructions"], tokens=d["model_chip_tokens"], segments=d["segments"], instr_per_s=d["instr_per_s"], gpu=d["gpu"].replace("NVIDIA ", ""), mode=d["mode"]))
    boot = json.load(open(os.path.join(ROOT, "docs/research/TRACES/model/boot.json")))
    out = dict(
        frames=frames, chunks=chunks, lanes=list(lanes.values()), typed=typed,
        totals=dict(
            frames=len(frames), frames_verified=sum(f["verified"] for f in frames),
            chunks=len(chunks), chunks_ok=sum(c["ok"] for c in chunks),
            instr=sum(c["instr"] for c in chunks), tokens=sum(c["tokens"] for c in chunks),
            wall_s=sum(c["wall_s"] for c in chunks), typed_instr=sum(t["instr"] for t in typed), typed_tokens=sum(t["tokens"] for t in typed),
            typed_segments=sum(t["segments"] for t in typed), min_frame_instr=min(f["instr"] for f in frames[1:]), max_frame_instr=max(f["instr"] for f in frames[1:]),
            last_frame_instr=frames[-1]["instr"], first_frame_instr=frames[0]["instr"],
        ),
        boot=dict(instr=boot["instructions"], segments=boot["segments"], tokens=boot["model_chip_tokens"], tok_per_instr=boot["tok_per_instr"], instr_per_s=boot["instr_per_s"], gpu=boot["gpu"].replace("NVIDIA ", "")),
    )
    dst = os.path.join(ROOT, "docs/derived/readme_data.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    json.dump(out, open(dst, "w"), indent=1)
    print("wrote", dst, out["totals"])


if __name__ == "__main__":
    sys.exit(main())
