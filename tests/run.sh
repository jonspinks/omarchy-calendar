#!/usr/bin/env bash
# Every test: the widget's logic under node, the sync's under python.
# Run from anywhere; nothing is written inside the plugin folder (the shell
# reloads the plugin on any change there).
set -euo pipefail
cd "$(dirname "$0")/.."
TZ=America/Toronto node tests/model.test.js
python3 -B -m unittest discover -s tests -p '*_test.py'
