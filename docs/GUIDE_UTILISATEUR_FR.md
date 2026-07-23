# Guide utilisateur CryptoGotchi v0.7.3

CryptoGotchi est un compagnon de suivi de marché créé par mikpoly pour Raspberry Pi Zero 2 W.

## Pages

### Marché

Affiche les actifs, prix, variations, graphiques, alertes et état du Raspberry.

### Compagnon

Affiche l’humeur, la progression, les interactions, la mémoire, les succès et le journal. L’analyse technique détaillée n’est plus mélangée à cette page.

### Analyse

1. Sélectionne un à cinq actifs.
2. Clique sur **Lancer l’analyse**.
3. Lis les trois lignes : **15 min**, **1 h**, **4 h**.
4. Pour chaque unité, CryptoGotchi affiche la structure, la tendance, le support, la résistance et son biais simulé.

Le biais global peut être :

- acheteur ;
- vendeur ;
- attente.

Il s’agit d’un avis ludique du compagnon, pas d’un conseil financier.

### Cryptos

Ajoute ou désactive les actifs. Cinquante actifs actifs sont recommandés sur le Pi Zero 2 W.

### Alertes

Configure le son du dashboard, Telegram, Discord, Mastodon, Bluesky ou un webhook. Les publications publiques restent désactivées tant que l’autorisation explicite n’est pas cochée.

### Réglages

Configure le Wi-Fi, le Bluetooth, le fuseau horaire, le LCD, l’IA facultative et le classement futur.

L’interrupteur Bluetooth ne modifie jamais le Wi-Fi ni SSH.

## Logo

Copie `logo.png` dans `/etc/cryptogotchi/logo.png`, puis redémarre le service. Le logo est affiché en 56 × 56 px.

## Commandes utiles

```bash
sudo systemctl status cryptogotchi --no-pager -l
sudo journalctl -u cryptogotchi -b --no-pager -n 150
curl -s http://127.0.0.1:8080/health
```

Projet communautaire : https://github.com/mikpoly/CryptoGotchi

Créateur : mikpoly — https://x.com/m_mikpoly
