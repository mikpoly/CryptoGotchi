# Installation

```bash
cd /home/mikpoly
sudo apt update
sudo apt install -y unzip
rm -rf CryptoGotchi-by-mikpoly
unzip CryptoGotchi-by-mikpoly-v0.7.3-community-safe.zip
cd CryptoGotchi-by-mikpoly
sudo bash scripts/install.sh
sudo reboot
```

Open `http://cryptogotchi.local:8080` and press `Ctrl+F5` after an upgrade.

The installer preserves `/etc/cryptogotchi/config.toml`, `/var/lib/cryptogotchi/cryptogotchi.db` and a custom logo.
