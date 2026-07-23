#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then echo "Lance ce script avec sudo." >&2; exit 1; fi
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR=/opt/cryptogotchi
CONFIG_DIR=/etc/cryptogotchi
DATA_DIR=/var/lib/cryptogotchi
IMAGE_BUILD=0
[[ "${1:-}" == "--image-build" ]] && IMAGE_BUILD=1

export DEBIAN_FRONTEND=noninteractive
apt-get update

# Debian/Raspberry Pi OS Trixie a supprimé le paquet binaire historique
# « policykit-1 ». Le service nécessaire aux règles NetworkManager se nomme
# désormais « polkitd ». On garde un fallback pour les anciennes images.
POLKIT_PACKAGE=""
if apt-cache show polkitd >/dev/null 2>&1; then
  POLKIT_PACKAGE=polkitd
elif apt-cache show policykit-1 >/dev/null 2>&1; then
  POLKIT_PACKAGE=policykit-1
else
  echo "Aucun paquet polkit compatible n'a été trouvé." >&2
  exit 1
fi

apt-get install -y \
  python3 python3-venv python3-pip python3-pil python3-flask \
  python3-requests python3-waitress avahi-daemon curl ca-certificates \
  sqlite3 network-manager bluez rfkill sudo python3-dbus python3-gi "$POLKIT_PACKAGE" fonts-dejavu-core

if ! apt-get install -y python3-spidev python3-lgpio; then
  apt-get install -y python3-spidev python3-rpi.gpio
fi

if ! id cryptogotchi >/dev/null 2>&1; then
  useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin cryptogotchi
fi
for grp in spi gpio i2c netdev video bluetooth; do
  getent group "$grp" >/dev/null || groupadd --system "$grp"
  usermod -aG "$grp" cryptogotchi
done

mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$DATA_DIR"

# Stop the running process before replacing its files. Keeping Python alive
# while overwriting modules can leave a partially upgraded installation.
systemctl stop cryptogotchi.service 2>/dev/null || true

# Keep timestamped backups before any schema migration or clean reinstall.
BACKUP_STAMP=$(date +%Y%m%d-%H%M%S)
if [[ -f "$DATA_DIR/cryptogotchi.db" ]]; then
  cp -a "$DATA_DIR/cryptogotchi.db" "$DATA_DIR/cryptogotchi.db.backup-$BACKUP_STAMP"
fi
if [[ -f "$CONFIG_DIR/config.toml" ]]; then
  cp -a "$CONFIG_DIR/config.toml" "$CONFIG_DIR/config.toml.backup-$BACKUP_STAMP"
fi
# Preserve a custom logo that may have been placed in the previous /opt tree.
if [[ -f "$INSTALL_DIR/logo.png" && ! -f "$CONFIG_DIR/logo.png" ]]; then
  cp -a "$INSTALL_DIR/logo.png" "$CONFIG_DIR/logo.png"
fi

# Replace the application tree completely. This prevents stale Python modules
# from an older patch remaining in /opt/cryptogotchi. Configuration and data
# live outside this directory and are preserved above.
find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -a "$SOURCE_DIR"/. "$INSTALL_DIR"/
rm -rf "$INSTALL_DIR/.venv"
python3 -m venv --system-site-packages "$INSTALL_DIR/.venv"
if ! "$INSTALL_DIR/.venv/bin/python" -c 'import flask, requests, waitress' >/dev/null 2>&1; then
  "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
fi

if [[ ! -f "$CONFIG_DIR/config.toml" ]]; then
  cp "$INSTALL_DIR/config/cryptogotchi.example.toml" "$CONFIG_DIR/config.toml"
fi
PYTHONPATH="$INSTALL_DIR" "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/scripts/migrate-config.py" "$CONFIG_DIR/config.toml"
chown -R cryptogotchi:cryptogotchi "$INSTALL_DIR" "$CONFIG_DIR" "$DATA_DIR"
chmod 750 "$CONFIG_DIR" "$DATA_DIR"
chmod 600 "$CONFIG_DIR/config.toml"

# Preflight the real application and the existing SQLite database before
# enabling/restarting systemd. This catches migration and import errors during
# installation rather than leaving the device in a restart loop.
if ! sudo -u cryptogotchi env \
  PYTHONPATH="$INSTALL_DIR" \
  CRYPTOGOTCHI_CONFIG="$CONFIG_DIR/config.toml" \
  CRYPTOGOTCHI_DATA_DIR="$DATA_DIR" \
  "$INSTALL_DIR/.venv/bin/python" -c \
  'from cryptogotchi.app import create_app; create_app(start_worker=False); print("CryptoGotchi application preflight OK")'; then
  echo "Échec du contrôle de démarrage. Les sauvegardes restent disponibles dans $CONFIG_DIR et $DATA_DIR." >&2
  exit 1
fi
if ! sudo -u cryptogotchi env PYTHONPATH="$INSTALL_DIR" \
  "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/scripts/preflight-technical.py"; then
  echo "Échec du contrôle de l’analyse technique. Installation interrompue avant le redémarrage du service." >&2
  exit 1
fi

install -m 0644 "$INSTALL_DIR/systemd/cryptogotchi.service" /etc/systemd/system/cryptogotchi.service
if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify /etc/systemd/system/cryptogotchi.service
fi
install -d -m 0755 /etc/polkit-1/rules.d
install -m 0644 "$INSTALL_DIR/systemd/cryptogotchi-networkmanager.rules" /etc/polkit-1/rules.d/49-cryptogotchi-networkmanager.rules

# Pairing and PAN profile creation require privileges on BlueZ/NetworkManager.
# The web service can only invoke this root-owned helper with a validated action
# and Bluetooth MAC address. No arbitrary command is accepted by the helper.
install -d -o root -g root -m 0755 /usr/local/lib/cryptogotchi
install -o root -g root -m 0755 "$INSTALL_DIR/scripts/cryptogotchi-bluetooth-agent.py" /usr/local/lib/cryptogotchi/cryptogotchi-bluetooth-agent.py
install -o root -g root -m 0755 "$INSTALL_DIR/scripts/cryptogotchi-bluetooth-helper" /usr/local/sbin/cryptogotchi-bluetooth-helper
install -o root -g root -m 0755 "$INSTALL_DIR/scripts/cryptogotchi-connectivity-watch" /usr/local/sbin/cryptogotchi-connectivity-watch
install -m 0644 "$INSTALL_DIR/systemd/cryptogotchi-bluetooth-agent.service" /etc/systemd/system/cryptogotchi-bluetooth-agent.service
install -m 0644 "$INSTALL_DIR/systemd/cryptogotchi-connectivity-watch.service" /etc/systemd/system/cryptogotchi-connectivity-watch.service
cat >/etc/sudoers.d/cryptogotchi-bluetooth <<'SUDOERS'
cryptogotchi ALL=(root) NOPASSWD: /usr/local/sbin/cryptogotchi-bluetooth-helper *
SUDOERS
chmod 0440 /etc/sudoers.d/cryptogotchi-bluetooth
visudo -cf /etc/sudoers.d/cryptogotchi-bluetooth >/dev/null

# Give the controller a stable phone-visible name and auto-enable it after boot.
mkdir -p /etc/bluetooth
if [[ -f /etc/bluetooth/main.conf ]]; then
  if grep -qE '^[#[:space:]]*AutoEnable=' /etc/bluetooth/main.conf; then
    sed -i 's/^[#[:space:]]*AutoEnable=.*/AutoEnable=true/' /etc/bluetooth/main.conf
  else
    printf '\n[Policy]\nAutoEnable=true\n' >>/etc/bluetooth/main.conf
  fi
fi

"$INSTALL_DIR/scripts/configure-lcd.sh"
systemctl daemon-reload
systemctl enable --now bluetooth.service || true
systemctl enable --now cryptogotchi-bluetooth-agent.service || true
systemctl enable --now cryptogotchi-connectivity-watch.service || true
bluetoothctl system-alias CryptoGotchi >/dev/null 2>&1 || true

# Upgrade PAN profiles created by v0.7.2 without deleting a working bnep link.
# Wi-Fi remains preferred through its usual metric 600; Bluetooth uses 750.
while IFS=: read -r profile type; do
  if [[ "$type" == "bluetooth" && "$profile" == CryptoGotchi\ Bluetooth\ * ]]; then
    nmcli connection modify "$profile" \
      connection.autoconnect yes \
      connection.autoconnect-priority 10 \
      connection.autoconnect-retries 0 \
      ipv4.route-metric 750 \
      connection.metered yes >/dev/null 2>&1 || true
  fi
done < <(nmcli -t -f NAME,TYPE connection show 2>/dev/null || true)

systemctl enable cryptogotchi.service
systemctl restart cryptogotchi.service

HEALTH_OK=0
for _ in $(seq 1 25); do
  if curl -fsS --max-time 2 http://127.0.0.1:8080/health >/tmp/cryptogotchi-install-health.json 2>/dev/null; then
    HEALTH_OK=1
    break
  fi
  sleep 1
done
if [[ $HEALTH_OK -ne 1 ]]; then
  echo "CryptoGotchi n'a pas répondu après l'installation." >&2
  systemctl --no-pager --full status cryptogotchi.service || true
  journalctl -u cryptogotchi.service -b --no-pager -n 80 || true
  exit 1
fi
cat /tmp/cryptogotchi-install-health.json
echo
systemctl enable --now avahi-daemon || true
systemctl enable --now bluetooth.service || true
HOSTNAME_CURRENT=$(hostname)
if [[ "$HOSTNAME_CURRENT" != "cryptogotchi" && $IMAGE_BUILD -eq 1 ]]; then
  hostnamectl set-hostname cryptogotchi || true
fi

echo
echo "CryptoGotchi installé."
echo "Interface: http://$(hostname).local:8080 ou http://ADRESSE_IP_DU_PI:8080"
echo "Au premier accès, crée le compte administrateur."
