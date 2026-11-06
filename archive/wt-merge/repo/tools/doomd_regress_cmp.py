#!/usr/bin/env python3
"""Comparison helpers of tools/doomd_regress.sh.

  doomd_regress_cmp.py diff NAME GOLDEN ACTUAL      first divergent line of two "<tic> <hash>" files
  doomd_regress_cmp.py tics NAME OUT_A.bin OUT_B.bin same "DOOMD_FRAME n tic t" sequence in two consoles
  doomd_regress_cmp.py orig NAME ORIG.h FRAMES.txt   frame hashes equal the original build's (aligned)
  doomd_regress_cmp.py stats NAME LOG BASELINE       print instr/tic + disk req/tic, warn vs baseline
Exit status 1 on a divergence (stats only on --fail-perf).
"""
import re, sys


def read(p):
    return [l.split() for l in open(p) if l.strip()]


def cmd_diff(name, golden, actual):
    g, a = read(golden), read(actual)
    n = min(len(g), len(a))
    for i in range(n):
        if g[i] != a[i]:
            print(f'FAIL {name}: first divergence at line {i + 1}: golden tic {g[i][0]} {g[i][1]} != actual tic {a[i][0]} {a[i][1]}'
                  f' ({sum(1 for k in range(n) if g[k] != a[k])} of {n} lines differ)')
            return 1
    if len(g) != len(a):
        print(f'FAIL {name}: golden has {len(g)} lines, actual {len(a)}')
        return 1
    print(f'ok   {name}: {len(g)} lines identical to golden')
    return 0


def cmd_tics(name, a, b):
    pat = re.compile(rb'DOOMD_FRAME (\d+) tic (\d+)')
    x, y = pat.findall(open(a, 'rb').read()), pat.findall(open(b, 'rb').read())
    if x != y:
        print(f'FAIL {name}: production build reaches different frames/tics than the check build ({len(x)} vs {len(y)} frames)')
        return 1
    print(f'ok   {name}: production and check build run the same {len(x)} frame/tic sequence')
    return 0


def cmd_orig(name, orig, frames):
    a = open(orig).read().split()
    b = [h for _, h in read(frames)]
    k = next((i for i in range(len(b)) if b[i] in a), None)
    if k is None:
        print(f'FAIL {name}: no frame in common with the original build')
        return 1
    j = a.index(b[k])
    n = min(len(a) - j - 1, len(b) - k - 1)   # the last frame of either may be cut off
    for i in range(n):
        if a[j + i] != b[k + i]:
            print(f'FAIL {name}: differs from the ORIGINAL build at aligned frame {i} (orig unique {j + i}, new {k + i})')
            return 1
    print(f'ok   {name}: {n} unique frames identical to the original build (aligned at new[{k}] = orig[{j}])')
    return 0


def parse_stats(log):
    t = open(log, errors='replace').read()
    r = {}
    m = re.search(r'GAMETICS n=(\d+) mean=(\d+) median=(\d+) p90=(\d+) max=(\d+)', t)
    if m:
        r.update(zip(('n', 'mean', 'median', 'p90', 'max'), map(int, m.groups())))
    m = re.search(r'DISK total_req=(\d+) req_per_tic=(\d+) bytes_per_tic=(\d+)', t)
    if m:
        r.update(zip(('disk_total', 'req_per_tic', 'bytes_per_tic'), map(int, m.groups())))
    return r


def cmd_stats(name, log, baseline, fail=False):
    r = parse_stats(log)
    if not r:
        print(f'FAIL {name}: no GAMETICS/DISK lines in {log}')
        return 1
    print(f'stat {name}: game tics n={r["n"]} instr/tic mean={r["mean"]} median={r["median"]} p90={r["p90"]} max={r["max"]}; '
          f'disk req/tic={r["req_per_tic"]} bytes/tic={r["bytes_per_tic"]} total req={r["disk_total"]}')
    rc = 0
    try:
        base = {}
        for l in open(baseline):
            p = l.split()
            if len(p) == 4 and p[0] == name:
                base = dict(mean=int(p[1]), req_per_tic=int(p[2]), n=int(p[3]))
        if base:
            for key, lim in (('mean', 1.05), ('req_per_tic', 1.10)):
                if r[key] > base[key] * lim:
                    print(f'{"FAIL" if fail else "WARN"} {name}: {key} {r[key]} is {100 * (r[key] / base[key] - 1):.1f}% above the baseline {base[key]}')
                    rc = 1 if fail else 0
            if r['mean'] < base['mean'] * 0.97:
                print(f'note {name}: mean instr/tic is {100 * (1 - r["mean"] / base["mean"]):.1f}% below the baseline {base["mean"]} (--update to adopt)')
    except FileNotFoundError:
        print(f'note {name}: no perf baseline file {baseline}')
    return rc


if __name__ == '__main__':
    c, args = sys.argv[1], sys.argv[2:]
    fail = '--fail-perf' in args
    args = [a for a in args if a != '--fail-perf']
    sys.exit({'diff': cmd_diff, 'tics': cmd_tics, 'orig': cmd_orig,
              'stats': lambda *a: cmd_stats(*a, fail=fail)}[c](*args))
