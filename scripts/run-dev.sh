#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CRYPTOGOTCHI_CONFIG="${CRYPTOGOTCHI_CONFIG:-$ROOT/.dev/config.toml}"
export CRYPTOGOTCHI_DATA_DIR="${CRYPTOGOTCHI_DATA_DIR:-$ROOT/.dev/data}"
mkdir -p "$(dirname "$CRYPTOGOTCHI_CONFIG")" "$CRYPTOGOTCHI_DATA_DIR"
python3 -m cryptogotchi
