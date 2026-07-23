#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo "Lance avec sudo." >&2; exit 1; fi
BOOT=/boot/firmware
[[ -d "$BOOT" ]] || BOOT=/boot
CONFIG="$BOOT/config.txt"
CMDLINE="$BOOT/cmdline.txt"

grep -q '^dtoverlay=dwc2' "$CONFIG" || echo 'dtoverlay=dwc2' >> "$CONFIG"
python3 - "$CMDLINE" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); line=p.read_text().strip()
needle='modules-load=dwc2,g_ether'
if needle not in line:
    parts=line.split(); parts.insert(1,needle); p.write_text(' '.join(parts)+'\n')
PY

apt-get update
apt-get install -y dnsmasq network-manager
mkdir -p /etc/dnsmasq.d
cat >/etc/dnsmasq.d/cryptogotchi-usb.conf <<'EOF'
interface=usb0
bind-dynamic
dhcp-range=10.0.0.1,10.0.0.1,255.255.255.0,12h
dhcp-option=3
dhcp-option=6
EOF

mkdir -p /etc/NetworkManager/system-connections
cat >/etc/NetworkManager/system-connections/cryptogotchi-usb.nmconnection <<'EOF'
[connection]
id=cryptogotchi-usb
type=ethernet
interface-name=usb0
autoconnect=true

[ipv4]
address1=10.0.0.2/24
method=manual
never-default=true

[ipv6]
method=disabled
EOF
chmod 600 /etc/NetworkManager/system-connections/cryptogotchi-usb.nmconnection
systemctl enable NetworkManager dnsmasq
systemctl restart NetworkManager dnsmasq || true

echo "Mode USB gadget activé. Redémarre le Pi, branche le port USB DATA, puis ouvre http://10.0.0.2:8080"
