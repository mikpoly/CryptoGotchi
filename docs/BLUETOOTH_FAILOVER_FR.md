# Wi-Fi et Bluetooth PAN — CryptoGotchi v0.7.3

## Différence entre Bluetooth connecté et Internet PAN actif

Un téléphone peut apparaître avec :

```text
Paired: yes
Connected: yes
```

sans fournir Internet au Raspberry Pi. Internet Bluetooth exige aussi une interface réseau `bnep0` avec une adresse IPv4.

État complet attendu :

```bash
nmcli -f NAME,TYPE,DEVICE,STATE connection show --active
ip -br address | grep -E "wlan0|bnep"
```

Exemple :

```text
netplan-wlan0-maison              wifi       wlan0  activated
CryptoGotchi Bluetooth 50D96E     bluetooth  bnep0  activated
```

## Priorité et basculement

CryptoGotchi configure le PAN avec une métrique IPv4 `750`. Le Wi-Fi Raspberry Pi utilise généralement `600`.

- métrique la plus faible : route utilisée ;
- Wi-Fi présent : `wlan0` est prioritaire ;
- Wi-Fi perdu : la route `bnep0` reste disponible ;
- Wi-Fi revenu : retour automatique vers `wlan0`.

Le dashboard ne choisit plus arbitrairement « Bluetooth ». Il lit la route réelle avec :

```bash
ip route get 1.1.1.1
```

## Correction du bouton Connecter Internet

La v0.7.2 supprimait puis recréait le profil, et déconnectait parfois BlueZ juste avant l’activation NetworkManager. Cela pouvait supprimer `bnep0` et produire :

```text
cannot find device bnep0
reason 'bluetooth-failed'
```

La v0.7.3 :

- conserve un profil valide ;
- modifie ses propriétés sans le supprimer ;
- détecte un PAN déjà actif ;
- ne lance plus `bluetoothctl disconnect` pendant la connexion ;
- active `connection.autoconnect=yes` ;
- retente au maximum deux fois avec une durée bornée.

## Désactivation sûre du Wi-Fi

La commande est refusée tant que ces conditions ne sont pas remplies :

- profil Bluetooth PAN actif ;
- interface `bnep` avec adresse IPv4 ;
- test Internet réussi sur cette interface.

Après la désactivation, `cryptogotchi-connectivity-watch.service` surveille le PAN. S’il disparaît, le Wi-Fi est réactivé automatiquement.

## Diagnostic

Depuis le dashboard, le bouton Diagnostic affiche :

- association et confiance BlueZ ;
- profil NetworkManager ;
- autoconnect et métrique ;
- connexions actives ;
- route Internet réelle ;
- adresse et passerelle PAN ;
- test Internet PAN ;
- journaux NetworkManager récents.

En terminal :

```bash
sudo /usr/local/sbin/cryptogotchi-bluetooth-helper diagnose AA:BB:CC:DD:EE:FF
```
