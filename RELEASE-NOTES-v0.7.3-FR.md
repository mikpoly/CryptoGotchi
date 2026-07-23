# Notes de version — CryptoGotchi v0.7.3

## Corrigé

- erreur PAN intermittente `cannot find device bnep0` ;
- bouton Connecter Internet qui recréait inutilement un profil fonctionnel ;
- confusion entre appareil Bluetooth connecté et partage Internet PAN actif ;
- dashboard affichant Bluetooth alors que la route Internet utilisait encore le Wi-Fi ;
- profils PAN sans reconnexion automatique ;
- détection de breakout sur la dernière bougie clôturée.

## Ajouté

- basculement automatique Wi-Fi prioritaire / Bluetooth de secours ;
- métrique PAN `750` ;
- reconnexion des profils PAN enregistrés ;
- interrupteur Wi-Fi protégé ;
- restauration automatique du Wi-Fi si le PAN disparaît ;
- affichage des connexions de secours ;
- diagnostic PAN enrichi ;
- tests de non-régression réseau.

## Compatibilité

La configuration, la base SQLite, le logo et les profils NetworkManager de la v0.7.1/v0.7.2 sont conservés.
