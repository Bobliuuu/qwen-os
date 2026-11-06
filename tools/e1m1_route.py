#!/usr/bin/env python3
"""Scripted key route for the E1M1 video (frames == game tics; rv32_fast -s format "F1-F2 key").
Keys are the real /bin/doomd keyboard keys (w fwd, a/d turn, q/r strafe, space fire, e use, z run);
T is the only debug key (teleport to the E1M1 door corridor, see qplat.c), ` prints a STATE line."""
import sys
ROUTE = [  # (first tic, last tic, key, comment)
 (2,   52,  "w",  "walk east from the start through the gate into the brown corridor"),
 (53,  190, "sp", "stand and fire the pistol at the two former humans coming down the corridor"),
 (100, 112, "q",  "strafe left (dodge)"),
 (125, 137, "r",  "strafe right (dodge)"),
 (191, 239, "w",  "walk to the corridor end, picking up bonuses/clip"),
 (191, 239, "z",  "run"),
 (240, 262, "d",  "turn right ~120 degrees to face back down the corridor"),
 (263, 420, "sp", "fire at the next monster"),
 (290, 300, "q",  "strafe left"),
 (320, 332, "r",  "strafe right"),
 (350, 360, "q",  "strafe left"),
 (421, 440, "w",  "walk back toward the start room"),
 (441, 441, "T",  "DEBUG KEY: teleport to the corridor in front of the shotgun-shell door"),
 (452, 454, "e",  "use: open the door"),
 (480, 506, "w",  "walk through the door into the dark room, pick up the shotgun shells"),
 (507, 540, "d",  "turn right ~180 degrees"),
 (541, 636, "w",  "walk back out through the door and along the corridor"),
 (637, 651, "a",  "turn left"),
 (652, 700, "w",  "walk out into the green outdoor area"),
 (653, 653, "g",  "DEBUG KEY: god mode on (outdoor imps killed the player in an earlier take)"),
 (701, 711, "a",  "turn left toward the barrels and the gray tower"),
 (712, 790, "sp", "fire the pistol at the explosive barrels"),
 (791, 850, "w",  "walk forward toward the pickups"),
 (851, 865, "a",  "turn left"),
 (866, 940, "w",  "walk on"),
 (941, 1060, "sp", "fire again (picks up and fires the pump-action shotgun)"),
]
NTICS = int(sys.argv[2]) if len(sys.argv) > 2 else 1150
if __name__ == "__main__":
    out = []
    for a, b, k, c in ROUTE:
        out.append(f"{a}-{b} {k}" if a != b else f"{a} {k}")
    for f in range(100, NTICS, 100): out.append(f"{f} `")
    open(sys.argv[1], "w").write("\n".join(out) + "\n")
