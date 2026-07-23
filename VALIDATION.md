# Validation CryptoGotchi v0.7.3 Community Connectivity

## Contrôles automatisés réalisés

```text
python -m compileall -q cryptogotchi scripts tests
bash -n scripts/install.sh
bash -n scripts/cryptogotchi-bluetooth-helper
bash -n scripts/cryptogotchi-connectivity-watch
PYTHONPATH=. pytest -q
```

Résultat :

```text
71 passed, 1 skipped
```

Le test ignoré dépend de Flask, absent de l’environnement de construction. L’installateur Raspberry Pi installe Flask puis exécute le préflight réel de l’application avant de redémarrer le service.

## Régressions couvertes

- route Internet réellement choisie par le noyau ;
- Wi-Fi prioritaire et Bluetooth PAN en secours ;
- profil PAN conservé et autoconnect activé ;
- absence de déconnexion BlueZ pendant `connect_pan` ;
- distinction entre Bluetooth connecté et PAN actif ;
- coupure Wi-Fi refusée sans PAN fonctionnel ;
- garde-fou de réactivation du Wi-Fi ;
- sérialisation JSON de l’analyse ;
- cassure haussière détectée depuis les bougies précédentes.

## Validation matérielle nécessaire

Les points suivants dépendent du Raspberry Pi et du téléphone :

- comportement du partage Bluetooth après redémarrage Android/iOS ;
- stabilité du lien `bnep0` dans un véhicule ;
- LCD Waveshare réel ;
- alimentation USB de la voiture ;
- fournisseurs de données et clés privées optionnelles.
