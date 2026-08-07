#!/bin/sh
set -eu

python3 -m unittest discover -s tests -v
(
  cd services/api
  python3 -m unittest test_search -v
)

if [ "${RUN_LIVE_GUIDE:-0}" = "1" ]; then
  RUN_LIVE_GUIDE=1 python3 -m unittest discover -s tests -v
else
  printf '\nLive checks skipped. Re-run with RUN_LIVE_GUIDE=1.\n'
fi
