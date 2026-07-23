# Installation sûre de CryptoGotchi v0.7.3

Cette édition est reconstruite depuis la v0.7.1 Final de secours.

## Garanties réseau du paquet

Les scripts ont été contrôlés afin de vérifier l’absence de commandes :

```text
rfkill block wifi
nmcli radio wifi off
systemctl stop ssh
systemctl disable ssh
```

L’option Bluetooth agit uniquement sur la radio Bluetooth.

## Installation

```bash
cd /home/mikpoly
sudo apt update
sudo apt install -y unzip
rm -rf CryptoGotchi-by-mikpoly
unzip CryptoGotchi-by-mikpoly-v0.7.3-community-safe.zip
cd CryptoGotchi-by-mikpoly
sudo bash scripts/install.sh
```

## Vérifications avant redémarrage

```bash
sudo systemctl status cryptogotchi --no-pager -l
curl -s http://127.0.0.1:8080/health
echo
hostname -I
```

La réponse `/health` doit contenir :

```json
{"ok":true,"version":"0.7.3"}
```

Puis :

```bash
sudo reboot
```

## Diagnostic

```bash
sudo journalctl -u cryptogotchi -b --no-pager -n 150
nmcli device status
systemctl is-active ssh
```
