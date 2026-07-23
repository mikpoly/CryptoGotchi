#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo "Lance avec sudo: sudo $0 AA:BB:CC:DD:EE:FF" >&2
  exit 1
fi
ADDRESS=${1:-}
HELPER=/usr/local/sbin/cryptogotchi-bluetooth-helper
if [[ -x "$HELPER" ]]; then
  exec "$HELPER" connect "$ADDRESS"
fi
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cryptogotchi-bluetooth-helper" connect "$ADDRESS"
