# Connexion USB réseau

Le script `scripts/enable-usb-gadget.sh` transforme le port **USB DATA** du Raspberry Pi Zero 2 W en interface réseau USB.

- adresse du Pi : `10.0.0.2` ;
- adresse proposée au PC : `10.0.0.1` ;
- interface Web : `http://10.0.0.2:8080` ;
- le Wi-Fi du Pi reste disponible pour accéder aux données de marché.

## Activation

```bash
sudo ./scripts/enable-usb-gadget.sh
sudo reboot
```

Branche ensuite un câble USB de données au port marqué **USB**, pas au port **PWR IN**.

## Windows

Windows doit faire apparaître une nouvelle carte réseau USB/RNDIS. Attends une à deux minutes après le démarrage, puis ouvre `http://10.0.0.2:8080`.

Vérification PowerShell :

```powershell
Get-NetAdapter
ping 10.0.0.2
```

## Linux

L'interface peut apparaître comme `usb0`, `enx...` ou un périphérique Ethernet USB. Ouvre directement `http://10.0.0.2:8080`.

## Dépannage

Sur le Pi :

```bash
ip address show usb0
lsmod | grep -E 'dwc2|g_ether'
sudo systemctl status NetworkManager dnsmasq cryptogotchi
```

Utilise un câble qui transporte les données : certains câbles ne servent qu'à la recharge.
