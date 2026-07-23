# Security policy

CryptoGotchi runs on a local Raspberry Pi and can store notification tokens in `/etc/cryptogotchi/config.toml`.

## Never publish these files

- `/etc/cryptogotchi/config.toml`
- `/var/lib/cryptogotchi/cryptogotchi.db` and its backups/WAL files
- diagnostic logs that contain private network names or device addresses
- Telegram bot tokens, Discord webhook URLs, Mastodon tokens, Bluesky App Passwords, ranking tokens or external-AI keys

Use dedicated, revocable credentials for every integration. CryptoGotchi never needs a wallet seed phrase, wallet private key or exchange withdrawal credential.

## Reporting a vulnerability

Do not post exploitable details or secrets in a public issue. Use a private GitHub security advisory for the repository when available. Include the affected version, reproduction steps, expected impact and a redacted log.

## Supported release

Security fixes target the latest published release. Community contributors should preserve CSRF protection, authentication, URL validation, output escaping and the privileged Bluetooth helper's strict action/MAC allow-list.
