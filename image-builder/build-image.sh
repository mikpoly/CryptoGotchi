#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${WORK:-$ROOT/.image-work}"
PI_GEN="$WORK/pi-gen"
PI_GEN_BRANCH="${PI_GEN_BRANCH:-master}"
mkdir -p "$WORK"
if [[ ! -d "$PI_GEN/.git" ]]; then
  git clone --depth 1 --branch "$PI_GEN_BRANCH" https://github.com/RPi-Distro/pi-gen.git "$PI_GEN"
else
  git -C "$PI_GEN" fetch --depth 1 origin "$PI_GEN_BRANCH"
  git -C "$PI_GEN" checkout -f "$PI_GEN_BRANCH"
  git -C "$PI_GEN" reset --hard "origin/$PI_GEN_BRANCH"
fi
rm -rf "$PI_GEN/stage-cryptogotchi"
cp -a "$ROOT/image-builder/stage-cryptogotchi" "$PI_GEN/stage-cryptogotchi"
tar --exclude='.git' --exclude='.image-work' --exclude='.venv' -czf "$PI_GEN/stage-cryptogotchi/00-install/files/cryptogotchi.tar.gz" -C "$ROOT" .
BUILD_PASS=$(openssl rand -hex 24)
cat >"$PI_GEN/config" <<EOF
IMG_NAME=CryptoGotchi-by-mikpoly-v0.7.3
RELEASE=trixie
DEPLOY_COMPRESSION=xz
LOCALE_DEFAULT=en_GB.UTF-8
KEYBOARD_KEYMAP=be
TIMEZONE_DEFAULT=Europe/Brussels
TARGET_HOSTNAME=cryptogotchi
WPA_COUNTRY=BE
FIRST_USER_NAME=cryptopi
FIRST_USER_PASS='$BUILD_PASS'
DISABLE_FIRST_BOOT_USER_RENAME=1
PASSWORDLESS_SUDO=0
ENABLE_SSH=0
ENABLE_CLOUD_INIT=0
STAGE_LIST="stage0 stage1 stage2 stage-cryptogotchi"
EOF
cd "$PI_GEN"
echo "Construction de l'image avec pi-gen. Docker est recommandé."
sudo ./build-docker.sh
find deploy -maxdepth 1 -type f -printf '%p\n'
