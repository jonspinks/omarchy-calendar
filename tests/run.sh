#!/usr/bin/env bash
# Every test: the widget's logic under node, the sync's under python.
# Run from anywhere; nothing is written inside the plugin folder (the shell
# reloads the plugin on any change there), and nothing touches your real
# accounts or cache: the XDG directories point at a throwaway one. (No test
# reaches the keyring or a server either; each stubs the sign-in and the HTTP.)
set -euo pipefail
cd "$(dirname "$0")/.."
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
export XDG_CONFIG_HOME="$scratch/config" XDG_CACHE_HOME="$scratch/cache" XDG_RUNTIME_DIR="$scratch/run"
mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
TZ=America/Toronto node tests/model.test.js
python3 -B -m unittest discover -s tests -p '*_test.py'
