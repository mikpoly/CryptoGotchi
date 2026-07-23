# Waveshare 1.44inch LCD HAT

Cette version cible le HAT couleur **128×128 ST7735S** photographié par l'utilisateur.

## Pilote intégré

Le fichier `cryptogotchi/hardware/lcd_1in44.py` pilote directement :

- SPI0 CE0 ;
- contrôleur ST7735S en RGB565 ;
- rétroéclairage ;
- joystick cinq directions ;
- boutons KEY1, KEY2 et KEY3.

Le pilote utilise `lgpio` sur Raspberry Pi OS récent et conserve un fallback `RPi.GPIO` pour les installations plus anciennes.

## Brochage BCM

| Fonction | GPIO BCM |
|---|---:|
| SPI SCLK | 11 |
| SPI MOSI | 10 |
| SPI CE0 / CS | 8 |
| LCD DC | 25 |
| LCD RESET | 27 |
| Rétroéclairage | 24 |
| Joystick haut | 6 |
| Joystick bas | 19 |
| Joystick gauche | 5 |
| Joystick droite | 26 |
| Appui joystick | 13 |
| KEY1 | 21 |
| KEY2 | 20 |
| KEY3 | 16 |

Le script `scripts/configure-lcd.sh` active SPI et configure les résistances pull-up des entrées dans `config.txt`.

## Test

Après installation et redémarrage :

```bash
sudo /opt/cryptogotchi/scripts/test-lcd.sh
```

Un motif coloré `LCD 1.44 OK` doit apparaître.

Vérifications utiles :

```bash
ls -l /dev/spidev0.0
sudo systemctl status cryptogotchi
sudo journalctl -u cryptogotchi -n 100 --no-pager
```

## Réglages

Dans l'interface Web, ouvre **Réglages → Écran** :

- type : `Waveshare LCD 1.44 ST7735S` ;
- rotation : 0, 90, 180 ou 270° ;
- luminosité normale ;
- luminosité réduite ;
- délai de réduction ;
- délai d'extinction ;
- durée de chaque page ;
- durée d'affichage prioritaire d'une alerte ;
- vitesse SPI.

La vitesse officielle de départ est `9000000` Hz. En cas d'artefacts, essaie `6000000` puis `4000000`.

## Pages

1. **Accueil** : visage, humeur et message contextuel.
2. **Crypto** : prix, variations et graphique d'une crypto.
3. **Marché** : vue condensée de la liste surveillée.
4. **Alerte** : dernière alerte et heure.
5. **Système** : IP, Wi-Fi, température, RAM et état des notifications.

## Remarques matérielles

- Coupe l'alimentation avant de monter ou retirer le HAT.
- Aligne correctement les 40 broches.
- Utilise une alimentation stable.
- Le premier démarrage après activation de SPI nécessite un redémarrage.
