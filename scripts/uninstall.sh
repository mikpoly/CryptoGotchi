#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo "Lance avec sudo." >&2; exit 1; fi
systemctl disable --now cryptogotchi.service || true
rm -f /etc/systemd/system/cryptogotchi.service
systemctl daemon-reload
rm -rf /opt/cryptogotchi
read -r -p "Supprimer aussi configuration et historique ? [y/N] " answer
[[ "$answer" =~ ^[Yy]$ ]] && rm -rf /etc/cryptogotchi /var/lib/cryptogotchi
echo "CryptoGotchi désinstallé."
