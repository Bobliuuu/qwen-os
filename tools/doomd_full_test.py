#!/usr/bin/env python3
"""Full-game feature tests of /bin/doomd on tools/rv32_fast (scripted keys, frame PNGs, STATE probes).
usage: doomd_full_test.py IMG_WITH_SAVE_DAT OUTDIR [--wad freedoom1.wad]
Writes OUTDIR/<feature>-<tag>.png and OUTDIR/results.txt (PASS/FAIL per feature). Needs the build with the
test-only keys (x exit, X secret exit, g god, i give all, t/T teleport, ` state)."""
import os, re, sys, shutil, subprocess, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doomd_play as P

START = "wait 10\ntap esc\ntap ent\ntap s\ntap s\ntap ent\nwait 60\n"      # menu -> New Game -> Hurt me plenty
def kv(line): return dict(x.split("=") for x in line.split())
def leave_level(): return "tap x\nwait 40\ntap e\ntap e\ntap e\ntap e\nwait 40\n"

SCEN = {}
SCEN["menu"] = ("wait 10\ndump title\ntap esc\ndump main_menu\ntap ent\ndump skill_menu\ntap esc\ntap esc\n"
                "tap s\ntap ent\ndump options_menu\ntap esc\ntap s\ntap s\ntap ent\ndump load_menu\ntap esc\n"
                "tap ent\ntap esc\ntap w\ntap ent\ndump quit_prompt\ntap n\ndump after_n\n", None)
SCEN["play"] = (START + "state\ndump e1m1_start\nhold w 60\nstate\ndump walk_forward\nhold d 20\nstate\ndump turn_right\n"
                "tap space\ntap space\nstate\ndump fire\ntap t\nhold w 14\nwait 10\nstate\ndump pickup_bonus\ntap T\ndump door_closed\n"
                "tap e\nwait 30\ndump door_opening\nwait 90\ndump door_open\nhold w 40\nwait 10\nstate\ndump pickup_shells_damage\n", None)
SCEN["levels"] = (START + "tap g\n" + "".join("state\ndump lvl_e1m%d\ntap x\nwait 40\nstate\ndump wi_stats_e1m%d\ntap e\ndump wi_stats2_e1m%d\ntap e\ntap e\ntap e\nwait 40\n" % (m, m, m) for m in range(1, 8))
                  + "state\ndump lvl_e1m8\ntap x\nwait 40\nstate\ndump finale_0\ntap e\ndump finale_1\ntap e\ntap e\ndump finale_2\ntap e\nwait 300\ndump finale_text\nstate\n", None)
SCEN["secret"] = (START + "tap g\n" + leave_level() + leave_level() + "state\ntap X\nwait 40\ndump wi_secret\ntap e\ntap e\ntap e\ntap e\nwait 40\nstate\ndump e1m9\n" + leave_level() + "state\ndump back_to_e1m4\n", None)
SCEN["save"] = (START + "hold w 30\nstate\ntap esc\ntap s\ntap s\ntap s\ndump save_menu\ntap ent\ndump save_slots\ntap ent\nwait 60\ndump game_saved\n", "SAVEOUT")
SCEN["load"] = ("wait 10\ntap esc\ntap s\ntap s\ntap ent\ndump load_slots\ntap ent\nwait 80\nstate\ndump loaded\nhold w 30\nstate\ndump loaded_walk\n", None)
SCEN["quit"] = ("wait 10\ntap esc\ntap w\ntap ent\ndump quit_prompt\ntap y\nwait 40\nstate\n", None)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("img"); ap.add_argument("out"); ap.add_argument("--wad"); ap.add_argument("--elf")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    res = []; img = a.img
    def check(name, ok, info=""):
        res.append("%s %s %s" % ("PASS" if ok else "FAIL", name, info)); print(res[-1])
    work = os.path.join(a.out, "_work"); os.makedirs(work, exist_ok=True)
    saved = os.path.join(work, "saved.img")
    R = {}
    for name, (scen, special) in SCEN.items():
        use = saved if name == "load" else img
        if name == "load" and not os.path.exists(saved): check("load", False, "no saved image"); continue
        pre = os.path.join(a.out, name)
        st, snd, raw, err = P.run(use, scen, pre, a.elf, a.wad, saved if special else None, quiet=True)
        R[name] = (st, snd, raw, err); S = [kv(s) for s in st]
        panic = b"PANIC" in raw or "FAULT" in err
        if name == "menu":
            check("menu_title_to_menu_skill_options_load_quit_prompt", not panic and os.path.exists(pre + "-quit_prompt.png"))
        if name == "play":
            ok_move = S[1]["x"] != S[0]["x"]
            check("move_forward", ok_move, "x %s -> %s" % (S[0]["x"], S[1]["x"]))
            check("turn", S[2]["ang"] != S[1]["ang"], "ang %s -> %s" % (S[1]["ang"], S[2]["ang"]))
            check("fire_ammo_decrements", int(S[3]["bul"]) < int(S[0]["bul"]), "bullets %s -> %s, sfx pistol(1) in %s" % (S[0]["bul"], S[3]["bul"], snd))
            check("pickup_health_bonus", int(S[4]["hp"]) > 100 and int(S[4]["items"]) >= 1, "hp %s items %s" % (S[4]["hp"], S[4]["items"]))
            xs = int(S[5]["x"], 16) >> 16
            check("door_open_and_walk_through", xs < 540, "player x=%d, door line at x=544..560 (frames door_closed/door_opening/door_open)" % xs)
            check("take_damage_from_monster", int(S[5]["hp"]) < int(S[4]["hp"]), "hp %s -> %s" % (S[4]["hp"], S[5]["hp"]))
            check("sound_events_emitted", len(snd) > 5 and 1 in snd, "ids %s" % snd[:20])
        if name == "levels":
            maps = [int(s["m"]) for s in S[0:15:2]]; gs = [int(s["gs"]) for s in S]
            check("levels_e1m1_to_e1m8_load_in_sequence", maps == [1, 2, 3, 4, 5, 6, 7, 8] and all(gs[i] == 0 for i in range(0, 16, 2)), "maps at level starts %s" % maps)
            check("intermission_after_each_exit", all(gs[i] == 1 for i in range(1, 14, 2)), "gamestate after exit %s (1 = intermission)" % gs[1:14:2])
            check("finale_after_e1m8", gs[-1] == 2, "gamestate %s (2 = finale)" % gs[-1])
        if name == "secret":
            check("secret_exit_e1m3_to_e1m9", int(S[-2]["m"]) == 9, "maps %s" % [s["m"] for s in S])
            check("e1m9_exit_returns_to_e1m4", int(S[-1]["m"]) == 4, "maps %s" % [s["m"] for s in S])
        if name == "save":
            check("savegame_writes_to_block_device", "diskwrites=" in err and not re.search(r"diskwrites=0\b", err) and os.path.exists(pre + "-game_saved.png"), err.strip().splitlines()[-1] if err.strip() else "")
        if name == "load":
            check("loadgame_from_saved_image_after_restart", not panic and int(S[0]["m"]) == 1 and S[1]["x"] != S[0]["x"], "x %s -> %s" % (S[0]["x"], S[1]["x"]))
        if name == "quit":
            check("quit_prompt_y_powers_off", b"power off" in raw, "")
        if panic: check(name + "_no_panic", False, err[:200])
    open(os.path.join(a.out, "results.txt"), "w").write("\n".join(res) + "\n")
    shutil.rmtree(work, ignore_errors=True)
main()
