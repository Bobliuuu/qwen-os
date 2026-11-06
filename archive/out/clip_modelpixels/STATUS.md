# Model-decoded pixel frames: status (written by the model-pixels agent, 22:05)
Frames being dumped through the real Qwen model (guest LCD dump -> console BYTE tokens, lockstep): 12,13,14,15 (batch 1, running since 21:44),
16,17,18,19 (batch 2, launching 22:05-22:20). Per-frame results are appended below as they finish. Other agents: skip these frames.
Frame n = n-th frame marker of the 45-frame clip; start state = out/model seg<n+3>.pkl.

## 22:25 results (frames byte-exact vs emulator, rows 0-199 = everything the dump carries; rows 200-239 status bar not in the dump)
12 DONE, 13 DONE, 14 DONE, 15 DONE (model BYTE tokens, lockstep, 0 divergence). 16-19 running, ETA ~22:45. Do not rerun 12-19.

## final-45 agent (22:50): I run frames 1-11 and 20-45 (everything not 12-19). Own work dir: out/clip_modelpixels/work, app qwenos-fp45
(fast kernels, K=64, one container per frame, results in modal volume qwenos-results/fp45/f<N>). Started: 1, 2, 20.

## FINAL 22:50: frames 12-19 all DONE (8 contiguous, view rows 0-199 byte-identical, lockstep, 0 divergence). Nothing running. 37 frames not done.
launched C: 5,6,24,29 (22:58); also running A: 1,2,20; B: 3,4,23
