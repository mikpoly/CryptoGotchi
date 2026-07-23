#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo "Lance ce script avec sudo." >&2; exit 1; fi
INSTALL_DIR=/opt/cryptogotchi
if [[ ! -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  echo "CryptoGotchi n'est pas installé dans /opt/cryptogotchi." >&2
  exit 1
fi
was_active=0
if systemctl is-active --quiet cryptogotchi.service; then
  was_active=1
  systemctl stop cryptogotchi.service
fi
cleanup(){
  if [[ $was_active -eq 1 ]]; then systemctl start cryptogotchi.service || true; fi
}
trap cleanup EXIT
cd "$INSTALL_DIR"
"$INSTALL_DIR/.venv/bin/python" -m cryptogotchi.lcd_test --seconds "${1:-8}"
