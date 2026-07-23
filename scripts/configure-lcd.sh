#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo "Lance ce script avec sudo." >&2; exit 1; fi
BOOT=/boot/firmware
[[ -d "$BOOT" ]] || BOOT=/boot
CONFIG="$BOOT/config.txt"
touch "$CONFIG"
grep -Eq '^dtparam=spi=on([[:space:]]|$)' "$CONFIG" || echo 'dtparam=spi=on' >> "$CONFIG"
grep -Eq '^gpio=6,19,5,26,13,21,20,16=pu([[:space:]]|$)' "$CONFIG" || echo 'gpio=6,19,5,26,13,21,20,16=pu' >> "$CONFIG"
if command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_spi 0 || true
fi
modprobe spi_bcm2835 2>/dev/null || true
printf 'SPI et résistances pull-up configurés pour le Waveshare 1.44inch LCD HAT.\n'
printf 'Un redémarrage est nécessaire si /dev/spidev0.0 n’existe pas encore.\n'
