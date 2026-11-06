#!/usr/bin/env python3
"""Per-episode test of the multi-episode disk: pick the episode in the menu, play through the maps the
pack has (exit key), spawn each boss type in front of the player, finale. usage: doomd_episode_test.py DISK OUTDIR [eps]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doomd_play as P
def kv(l): return dict(x.split("=") for x in l.split())
def leave(): return "tap x\nwait 40\ntap e\ntap e\ntap e\ntap e\nwait 40\n"
def scen(ep, maps):
    t = "wait 10\ntap esc\ntap ent\n" + "tap s\n" * (ep - 1) + "dump ep%d_menu\ntap ent\ntap s\ntap s\ntap ent\nwait 80\ntap g\n" % ep
    t += "state\ndump m1\n"
    ALL = {"h": "cacodemon", "b": "baron", "c": "cyberdemon", "k": "spider", "l": "lostsoul"}
    # only the monsters of the pack's roster have sprites in its image
    HAVE = {1: "bl", 2: "hbcl", 3: "hbckl", 4: "hbckl"}[ep]
    for k in HAVE:
        key = ALL[k]
        t += "tap %s\nwait 30\ndump spawn_%s\n" % (k, key)
    t += "hold w 40\nstate\ndump walk\n"
    for i, m in enumerate(maps):
        if i: t += "state\ndump m%d\n" % m
        t += "tap x\nwait 40\nstate\ndump wi_m%d\ntap e\ntap e\ntap e\ntap e\nwait 60\n" % m
    t += "state\ndump after_last\nwait 400\ndump finale_text\nstate\n"
    return t
def main():
    disk, out = sys.argv[1], sys.argv[2]; eps = [int(c) for c in (sys.argv[3] if len(sys.argv) > 3 else "1234")]
    os.makedirs(out, exist_ok=True); res = []
    PLAY = {1: range(1, 9), 2: range(1, 9), 3: range(1, 9), 4: [1, 3, 4, 5, 8]}
    for ep in eps:
        maps = list(PLAY[ep]); pre = os.path.join(out, "ep%d" % ep)
        st, snd, raw, err = P.run(disk, scen(ep, maps), pre, quiet=True)
        S = [kv(s) for s in st]; panic = b"PANIC" in raw or "FAULT" in err
        if panic:
            import re as _re
            m = _re.search(rb"PANIC: ([^\n]*)", raw); print("ep%d panic: %s" % (ep, m.group(1).decode() if m else err[:80]))
        if not S: res.append("FAIL ep%d no state" % ep); continue
        # states: [m1 start, after walk, (m_i start, m_i intermission) ..., after_last, finale_text]
        seq = [int(s["m"]) for s in S]; gs = [int(s["gs"]) for s in S]
        ok_ep = all(s["e"] == str(ep) for s in S[:-1] if s["gs"] != "3")
        res.append("%s ep%d_loads_and_plays_maps %s episode=%s maps=%s gs=%s tk=%s%s" % ("PASS" if ok_ep and not panic and gs[-1] == 2 else "FAIL", ep, maps, S[0]["e"], seq, gs, S[0].get("tk"), " PANIC" if panic else ""))
        print(res[-1])
    open(os.path.join(out, "results.txt"), "w").write("\n".join(res) + "\n")
main()
