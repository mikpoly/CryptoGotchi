# Contribuer à CryptoGotchi

CryptoGotchi est un projet communautaire créé par **mikpoly**.

- Dépôt : https://github.com/mikpoly/CryptoGotchi
- Actualités : https://x.com/m_mikpoly

Les issues et Pull Requests sont bienvenues.

## Principes

- conserver la structure du code et les fonctions publiques existantes autant que possible ;
- viser le Raspberry Pi Zero 2 W 32 bits en priorité ;
- rester léger en mémoire, CPU, appels API et écritures microSD ;
- ne jamais stocker de seed phrase, clé privée ou mot de passe en clair ;
- ne jamais désactiver le Wi-Fi ou SSH sans action explicite et documentée ;
- séparer les actions Bluetooth des commandes Wi-Fi ;
- ajouter des tests à toute nouvelle règle de marché, notification ou fonction matérielle ;
- conserver le mode virtuel pour développer sans Raspberry Pi.

## Avant une Pull Request

```bash
python -m compileall -q cryptogotchi scripts tests
bash -n scripts/install.sh
bash -n scripts/cryptogotchi-bluetooth-helper
PYTHONPATH=. pytest -q
```

Utilise le modèle `.github/PULL_REQUEST_TEMPLATE.md` et décris précisément les fonctions modifiées.
