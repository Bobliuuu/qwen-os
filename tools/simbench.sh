#!/bin/bash
# tools/simbench.sh NAME : build + run the compiler_bench config and print steps/tokens/md5 (host emulator only).
# Same as tools/compiler_bench.sh; fails if md5/fbmd5 differ from the perf/compiler baseline.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
R=$(tools/compiler_bench.sh "$1" | tail -1); echo "$R"
case "$R" in *md5=1b7e17987e2a839475b44ae635e1f03e*fbmd5=2098581f19352ac314ee60ff2e1c28fd*) echo "HASH OK";; *) echo "HASH MISMATCH"; exit 1;; esac
