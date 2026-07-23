<p align="center">
  <img src="main/cryptogotchi/logo.png" width="180">
</p>  

# CryptoGotchi by mikpoly


CryptoGotchi is a community-driven market-tracking companion for Raspberry Pi Zero 2 W with a Waveshare 1.44-inch LCD.

Created by mikpoly:

GitHub: https://github.com/mikpoly/CryptoGotchi

X / Twitter: https://x.com/m_mikpoly

CryptoGotchi is an open-source community project. Fixes, translations, tests, ideas and improvements can be submitted through Pull Requests.

CryptoGotchi monitors markets and generates a simulated companion bias. It does not place orders. The “buy / sell / wait” messages are not financial advice.

Version 0.7.3 — Community Connectivity Edition

This version is based on the stable v0.7.2 Community Safe release and fixes the Bluetooth PAN behavior observed on Raspberry Pi OS Trixie with NetworkManager.

Main network fixes

the Connect Internet button no longer deletes an already working PAN profile;

an active bnep0 interface is detected and preserved;

the Bluetooth PAN profile is saved with automatic reconnection enabled;

Wi-Fi remains the preferred connection with the usual metric of 600;

Bluetooth PAN uses a metric of 750 and remains available as a fallback;

when Wi-Fi disappears, Linux automatically uses the active Bluetooth route;

when Wi-Fi returns, it becomes the preferred route again;

the dashboard displays the actual Internet route in use, read from the Linux routing table;

standard Bluetooth status and Internet PAN status are now shown separately;

diagnostics display the bnep interface, IPv4 address, gateway and an Internet test;

a protected Wi-Fi switch has been added;

Wi-Fi can only be disabled when a working Bluetooth PAN connection is already active;

a safety guard automatically restores Wi-Fi if the PAN connection disappears;

a lightweight service retries saved PAN profiles configured with autoconnect=yes.

Analysis and companion

dedicated Analysis page, separate from the Companion page;

clear timeframes: 15 minutes, 1 hour and 4 hours;

support, resistance, trend, range and breakout for each timeframe;

playful bias: buy, sell or wait;

improved breakout detection using the most recently closed candle;

custom logo.png displayed at 56 × 56 px.

Recommended hardware

Raspberry Pi Zero 2 W;

Raspberry Pi OS Lite 32-bit or 64-bit;

Waveshare 1.44inch LCD HAT ST7735S;

microSD card with at least 8 GB.

Installation

Transfer the ZIP archive to /home/mikpoly, then run:

cd /home/mikpoly
sudo apt update
sudo apt install -y unzip
rm -rf CryptoGotchi-by-mikpoly
unzip CryptoGotchi-by-mikpoly-v0.7.3-community-connectivity.zip
cd CryptoGotchi-by-mikpoly
sudo bash scripts/install.sh
sudo reboot

After about one minute, open:

http://cryptogotchi.local:8080

The installer automatically preserves:

/etc/cryptogotchi/config.toml;

/var/lib/cryptogotchi/cryptogotchi.db;

the custom logo;

existing NetworkManager profiles.

Wi-Fi / Bluetooth failover

Pair your phone with the Raspberry Pi.

Enable mobile data or Wi-Fi on the phone.

Enable Bluetooth tethering on Android, or a compatible Bluetooth tethering mode on iPhone.

In CryptoGotchi, click Connect Internet.

Click Scan phones and check that the status shows Internet PAN active · bnep0.

When both connections are active:

Wi-Fi wlan0      metric 600  → preferred route
Bluetooth bnep0  metric 750  → fallback route

Bluetooth tethering must remain enabled on the phone. Some phones disable it automatically after a reboot or a period of inactivity; CryptoGotchi cannot change this Android or iOS setting remotely.

Radio switches

Bluetooth

The Bluetooth switch only controls Bluetooth. It never disables Wi-Fi or SSH.

Wi-Fi

The Wi-Fi switch is intentionally protected:

without an active and tested Bluetooth PAN connection, Wi-Fi shutdown is refused;

if PAN disappears after Wi-Fi is disabled, the guard service restores Wi-Fi;

Bluetooth is not modified by the Wi-Fi switch.

Useful checks

nmcli -f NAME,TYPE,DEVICE,STATE connection show --active
ip -br address | grep -E "wlan0|bnep"
ip route
ip route get 1.1.1.1
curl -s http://127.0.0.1:8080/health

Community development

python -m compileall -q cryptogotchi scripts tests
bash -n scripts/install.sh
bash -n scripts/cryptogotchi-bluetooth-helper
bash -n scripts/cryptogotchi-connectivity-watch
PYTHONPATH=. pytest -q

Before submitting a Pull Request:

do not remove existing features without a clear reason;

never commit tokens, passwords, seed phrases or private data;

verify the project on a Raspberry Pi Zero 2 W;

add or update tests;

clearly explain which files were changed.

See CONTRIBUTING.md, .github/PULL_REQUEST_TEMPLATE.md, docs/BLUETOOTH_FAILOVER_FR.md and SECURITY.md.





 -------------------------------------------------------------------------------FRANCAIS -------------------------------------------------------------------------------





CryptoGotchi est un compagnon communautaire de suivi de marché pour **Raspberry Pi Zero 2 W** avec écran **Waveshare LCD 1,44 pouce**.

Créé par **mikpoly** :

- GitHub : https://github.com/mikpoly/CryptoGotchi
- X / Twitter : https://x.com/m_mikpoly

Le projet est open source et communautaire. Les corrections, traductions, tests, idées et améliorations peuvent être proposées par **Pull Request**.

> CryptoGotchi observe les marchés et produit un biais simulé du compagnon. Il ne passe aucun ordre. Les phrases « acheteur / vendeur / attente » ne sont pas des conseils financiers.

## Version 0.7.3 — Community Connectivity Edition

Cette version repart de la base stable v0.7.2 Community Safe et corrige le comportement Bluetooth PAN observé sur Raspberry Pi OS Trixie avec NetworkManager.

### Corrections réseau principales

- le bouton **Connecter Internet** ne supprime plus un profil PAN déjà fonctionnel ;
- un `bnep0` déjà actif est détecté et conservé ;
- le profil Bluetooth PAN est enregistré avec reconnexion automatique ;
- le Wi-Fi reste prioritaire avec une métrique habituelle de `600` ;
- le Bluetooth PAN utilise une métrique de `750` et reste en secours ;
- lorsque le Wi-Fi disparaît, Linux utilise automatiquement la route Bluetooth encore active ;
- lorsque le Wi-Fi revient, il reprend la priorité ;
- le dashboard affiche la **route Internet réellement utilisée**, obtenue depuis la table de routage Linux ;
- l’état Bluetooth classique et l’état Internet PAN sont maintenant distingués ;
- un diagnostic affiche l’interface `bnep`, l’adresse IPv4, la passerelle et un test Internet ;
- ajout d’un interrupteur Wi-Fi protégé ;
- le Wi-Fi ne peut être désactivé que si un PAN Bluetooth fonctionnel est déjà actif ;
- un garde-fou réactive automatiquement le Wi-Fi si le PAN disparaît ;
- un service léger retente les profils PAN enregistrés avec `autoconnect=yes`.

### Analyse et compagnon

- page **Analyse** séparée de la page **Compagnon** ;
- unités lisibles : **15 min, 1 h et 4 h** ;
- support, résistance, tendance, range et breakout par unité ;
- biais ludique : **acheteur, vendeur ou attente** ;
- correction de la détection d’une cassure sur la dernière bougie clôturée ;
- logo `logo.png` affiché en **56 × 56 px**.

## Matériel recommandé

- Raspberry Pi Zero 2 W ;
- Raspberry Pi OS Lite 32 bits ou 64 bits ;
- Waveshare 1.44inch LCD HAT ST7735S ;
- carte microSD de 8 Go minimum.

## Installation

Transfère le ZIP dans `/home/mikpoly`, puis :

```bash
cd /home/mikpoly
sudo apt update
sudo apt install -y unzip
rm -rf CryptoGotchi-by-mikpoly
unzip CryptoGotchi-by-mikpoly-v0.7.3-community-connectivity.zip
cd CryptoGotchi-by-mikpoly
sudo bash scripts/install.sh
sudo reboot
```

Après environ une minute :

```text
http://cryptogotchi.local:8080
```

L’installateur sauvegarde automatiquement :

- `/etc/cryptogotchi/config.toml` ;
- `/var/lib/cryptogotchi/cryptogotchi.db` ;
- le logo personnalisé ;
- les profils NetworkManager existants.

## Utilisation du basculement Wi-Fi / Bluetooth

1. Associe le téléphone au Raspberry Pi.
2. Active les données mobiles ou le Wi-Fi du téléphone.
3. Active **Partage de connexion Bluetooth** sur Android, ou le partage de connexion compatible Bluetooth sur iPhone.
4. Dans CryptoGotchi, clique sur **Connecter Internet**.
5. Clique sur **Scanner les téléphones** pour vérifier que l’état affiche `Internet PAN actif · bnep0`.

Lorsque les deux liens sont actifs :

```text
Wi-Fi wlan0      métrique 600  → route prioritaire
Bluetooth bnep0  métrique 750  → route de secours
```

Le téléphone doit garder son partage Bluetooth activé. Certains téléphones désactivent automatiquement ce partage après un redémarrage ou une période d’inactivité ; CryptoGotchi ne peut pas modifier ce réglage Android/iOS à distance.

## Interrupteurs radio

### Bluetooth

L’interrupteur Bluetooth agit seulement sur Bluetooth. Il ne coupe jamais le Wi-Fi ni SSH.

### Wi-Fi

L’interrupteur Wi-Fi est volontairement protégé :

- sans PAN Bluetooth actif et testé, la coupure est refusée ;
- si le PAN disparaît après la coupure, le service de garde réactive le Wi-Fi ;
- le Bluetooth n’est pas modifié par l’interrupteur Wi-Fi.

## Vérifications utiles

```bash
nmcli -f NAME,TYPE,DEVICE,STATE connection show --active
ip -br address | grep -E "wlan0|bnep"
ip route
ip route get 1.1.1.1
curl -s http://127.0.0.1:8080/health
```

## Développement communautaire

```bash
python -m compileall -q cryptogotchi scripts tests
bash -n scripts/install.sh
bash -n scripts/cryptogotchi-bluetooth-helper
bash -n scripts/cryptogotchi-connectivity-watch
PYTHONPATH=. pytest -q
```

Avant une Pull Request :

1. ne supprime pas les fonctions existantes sans justification ;
2. ne mets jamais de token, mot de passe, seed phrase ou donnée privée dans le dépôt ;
3. vérifie le fonctionnement sur Pi Zero 2 W ;
4. ajoute ou adapte les tests ;
5. explique clairement les fichiers modifiés.

Consulte `CONTRIBUTING.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `docs/BLUETOOTH_FAILOVER_FR.md` et `SECURITY.md`.
