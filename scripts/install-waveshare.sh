#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo "Lance avec sudo." >&2; exit 1; fi
apt-get update
apt-get install -y git python3-pil python3-numpy python3-spidev python3-gpiozero
TMP=$(mktemp -d)
git clone --depth 1 https://github.com/waveshareteam/e-Paper.git "$TMP/e-Paper"
SITE=$(/opt/cryptogotchi/.venv/bin/python -c 'import site; print(site.getsitepackages()[0])')
cp -a "$TMP/e-Paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd" "$SITE/"
rm -rf "$TMP"
raspi-config nonint do_spi 0 || true
systemctl restart cryptogotchi

echo "Pilotes e-paper Waveshare installés. Choisis 'Waveshare e-paper' dans Réglages."
