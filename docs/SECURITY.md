# Sécurité

- L'interface est destinée à un réseau privé. Ne redirige pas le port 8080 sur Internet.
- Le mot de passe est stocké sous forme de hash Werkzeug.
- Toutes les modifications Web utilisent un jeton CSRF.
- Des en-têtes de sécurité empêchent notamment l'intégration de l'interface dans une frame.
- Les secrets sont conservés dans `/etc/cryptogotchi/config.toml` avec le mode `600`.
- Utilise uniquement des tokens dédiés et révocables.
- N'entre jamais de seed phrase, de clé privée, ni de clé d'exchange avec permission de retrait ou de trading.
- Mastodon et Bluesky restent bloqués tant que l'autorisation générale et l'autorisation de la crypto ne sont pas actives.
- Le nombre de publications publiques par heure est limité.
- L'utilisateur système ne reçoit que les autorisations NetworkManager nécessaires au scan et à la connexion Wi-Fi.
- Le projet ne donne pas de conseil financier et ne passe aucun ordre.

## Sauvegarde sûre

Tu peux sauvegarder la configuration localement, mais ne l'ajoute jamais à un dépôt public :

```bash
sudo cp /etc/cryptogotchi/config.toml ~/cryptogotchi-config-backup.toml
sudo chown "$USER":"$USER" ~/cryptogotchi-config-backup.toml
chmod 600 ~/cryptogotchi-config-backup.toml
```
