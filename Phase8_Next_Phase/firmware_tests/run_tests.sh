#!/usr/bin/env bash
# Builds and runs the Phase 8 firmware tests on a PC (Linux/macOS, g++ or clang++).
#   bash Phase8_Next_Phase/firmware_tests/run_tests.sh
# Each test runs in its own process so the sketch globals start fresh.
set -euo pipefail
cd "$(dirname "$0")"
CXX=${CXX:-g++}
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT
FLAGS="$(cat build_flags.txt) -Werror"

echo "== sentry_common.h copies are identical"
cmp ../Phase8_RX_Node/sentry_common.h ../Phase8_Alert_Station/sentry_common.h
echo "   ok"

fail=0
run_suite() {  # name source
  local name=$1 src=$2
  echo "== $name"
  $CXX $FLAGS -x c++ "$src" mock/mock.cpp -o "$OUT/$name"
  for t in $(grep -oE '^TEST\(([a-z0-9_]+)\)' "$src" | sed -E 's/TEST\((.*)\)/\1/'); do
    if ! ONLY=$t "$OUT/$name" | grep -E '^(ok|FAIL|  FAIL)'; then fail=1; fi
    ONLY=$t "$OUT/$name" > /dev/null || fail=1
  done
}
run_suite common test_common.cpp
run_suite rx_node test_rx_node.cpp
run_suite alert_station test_alert_station.cpp

if [ $fail -ne 0 ]; then echo "SOME TESTS FAILED"; exit 1; fi
echo "ALL FIRMWARE TESTS PASSED"
