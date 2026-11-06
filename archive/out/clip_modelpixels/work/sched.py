#!/usr/bin/env python3
"""Launch one single-container modal run per queued frame whenever fewer than CAP containers are active (all agents). Retries a frame once if its run fails."""
import os, subprocess, sys, time
W = '/Users/jhome/qwenos-work/out/clip_modelpixels/work'
CAP = 10
queue = [int(x) for x in sys.argv[1].split(',')]
retries = {}
procs = {}     # frame -> Popen
start = {}

def active():
    out = subprocess.run(['modal', 'container', 'list'], capture_output=True, text=True).stdout
    return sum(1 for l in out.splitlines() if 'ta-' in l)

while queue or procs:
    for f, p in list(procs.items()):
        if p.poll() is not None:
            del procs[f]
            if p.returncode != 0 and retries.get(f, 0) < 1:
                retries[f] = retries.get(f, 0) + 1; queue.insert(0, f); print('requeue', f, flush=True)
            else:
                print('finished', f, p.returncode, time.strftime('%H:%M:%S'), flush=True)
    try:
        n = active()
    except Exception as e:
        print('list failed', e, flush=True); time.sleep(30); continue
    recent = sum(1 for f in procs if time.time() - start[f] < 150)
    free = CAP - n - recent
    while queue and free > 0:
        f = queue.pop(0)
        env = dict(os.environ, FP_MAXC='1')
        tag = os.environ.get('TAG', 'fp45r')
        procs[f] = subprocess.Popen(['modal', 'run', 'modal_fp45.py', '--tag', tag, '--frames', str(f)], cwd=W, env=env,
                                    stdout=open(f'{W}/logs/modal_f{f}.log', 'w'), stderr=subprocess.STDOUT)
        start[f] = time.time()
        print('launched', f, time.strftime('%H:%M:%S'), flush=True); free -= 1
        time.sleep(20)   # let the container appear in the list before recounting
    time.sleep(45)
