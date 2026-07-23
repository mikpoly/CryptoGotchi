#!/bin/bash -e
install -m 0644 files/cryptogotchi.tar.gz "${ROOTFS_DIR}/tmp/cryptogotchi.tar.gz"
on_chroot <<'EOF'
mkdir -p /tmp/cryptogotchi-src
cd /tmp/cryptogotchi-src
tar -xzf /tmp/cryptogotchi.tar.gz
./scripts/install.sh --image-build
./scripts/enable-usb-gadget.sh
passwd -l cryptopi || true
cp config/cryptogotchi.example.toml /boot/firmware/cryptogotchi.toml 2>/dev/null || cp config/cryptogotchi.example.toml /boot/cryptogotchi.toml
rm -rf /tmp/cryptogotchi-src /tmp/cryptogotchi.tar.gz
EOF
