# Base de secours et sécurité réseau

La v0.7.2 Community Safe a été reconstruite directement depuis l’archive de secours fournie :

```text
CryptoGotchi-by-mikpoly-v0.7.1-final(1).zip
SHA-256 : 6eb72e3fa8c7e5e003e86e86e275f2042cd611ef4802e2cfca9ef35408c0f2aa
```

Les changements applicatifs sont limités aux fonctions demandées :

- page Analyse séparée ;
- unités 15 min, 1 h et 4 h ;
- biais acheteur, vendeur ou attente ;
- logo agrandi ;
- interrupteur Bluetooth ;
- documentation communautaire.

## Audit réseau

Les scripts exécutables ne contiennent aucune commande qui :

- bloque le Wi-Fi ;
- éteint la radio Wi-Fi ;
- arrête SSH ;
- désactive SSH.

Le bouton Bluetooth utilise uniquement :

```text
rfkill unblock bluetooth
rfkill block bluetooth
bluetoothctl power on/off
```

Il ne lance aucune commande `wifi off`, `radio all off` ou `rfkill block wifi`.
