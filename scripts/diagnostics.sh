#!/usr/bin/env bash
set -u

echo "=== CryptoGotchi diagnostics ==="
echo "Date: $(date -Is)"
echo "Host: $(hostname)"
echo "Kernel: $(uname -a)"
echo "Model: $(tr -d '\0' </proc/device-tree/model 2>/dev/null || echo inconnu)"
echo "IP: $(hostname -I 2>/dev/null)"
echo "SPI:"
ls -l /dev/spidev* 2>&1 || true
lsmod | grep -E 'spi_bcm|spidev|dwc2|g_ether' || true
echo "GPIO chips:"
ls -l /dev/gpiochip* 2>&1 || true
echo "Groupes cryptogotchi:"
id cryptogotchi 2>&1 || true
echo "Configuration écran:"
grep -A14 '^\[display\]' /etc/cryptogotchi/config.toml 2>/dev/null || true
echo "Service:"
systemctl --no-pager --full status cryptogotchi 2>&1 | tail -n 35
echo "Health:"
curl -sS http://127.0.0.1:8080/health || true
echo
echo "Logs:"
journalctl -u cryptogotchi --no-pager -n 100
