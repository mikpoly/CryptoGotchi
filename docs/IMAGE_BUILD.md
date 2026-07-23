# Construire une image `.img.xz` flashable

Le dossier `image-builder` ajoute CryptoGotchi à Raspberry Pi OS Lite avec `pi-gen`.

## Résultat de l'image

- Raspberry Pi OS Lite 32 bits Trixie ;
- profil Pi Zero 2 W ;
- pilote Waveshare 1.44inch LCD HAT actif ;
- service CryptoGotchi actif au démarrage ;
- SPI actif ;
- interface USB réseau `10.0.0.2` active ;
- SSH désactivé ;
- administration initiale par navigateur ;
- fichier `cryptogotchi.toml` visible dans la partition boot.

## Prérequis

- machine Linux Debian/Ubuntu 64 bits ;
- Docker fonctionnel ;
- `git`, `openssl`, `tar` et `sudo` ;
- environ 35 Go d'espace libre ;
- accès Internet pendant la construction.

## Construction

```bash
sudo ./image-builder/build-image.sh
```

Le résultat est attendu dans :

```text
.image-work/pi-gen/deploy/
```

La branche pi-gen peut être changée ainsi :

```bash
PI_GEN_BRANCH=master sudo -E ./image-builder/build-image.sh
```

## Premier démarrage

1. Flashe le `.img.xz` avec Balena Etcher ou Raspberry Pi Imager.
2. Monte le HAT et insère la carte.
3. Branche le port USB DATA au PC.
4. Attends le premier démarrage, qui peut prendre plusieurs minutes.
5. Ouvre `http://10.0.0.2:8080`.
6. Crée le compte administrateur.
7. Connecte le Wi-Fi depuis **Réglages**.

## Validation obligatoire avant publication

Une image ne doit pas être publiée comme stable sans vérifier sur le matériel réel :

- affichage et couleurs ;
- joystick et trois boutons ;
- Wi-Fi ;
- connexion USB sur Windows/Linux ;
- redémarrage et arrêt ;
- récupération après coupure Internet ;
- fonctionnement pendant plusieurs heures ;
- taille des journaux et de la base SQLite.
