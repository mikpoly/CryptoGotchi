# CryptoGotchi community ranking API v1

The client is implemented in `cryptogotchi/ranking.py` and is disabled by default.

## Endpoint

Configure one HTTPS POST endpoint, for example:

```text
https://community.example/api/v1/cryptogotchi/ranking
```

The URL must use HTTPS and may not contain embedded credentials.

## Request

Headers:

```text
Content-Type: application/json
Accept: application/json
X-CryptoGotchi-Protocol: 1
User-Agent: CryptoGotchi-by-mikpoly/0.7.0
Authorization: Bearer <token>                 # only when configured
X-CryptoGotchi-Signature: <hex HMAC-SHA256>  # only when token is configured
```

The HMAC is computed over the exact compact JSON request body using the configured token as the key.

Example body:

```json
{
  "protocol_version": 1,
  "device_id": "random-pseudonymous-id",
  "public_name": "My CryptoGotchi",
  "app_version": "0.7.0",
  "level": 9,
  "xp": 964,
  "observations": 1450,
  "achievement_count": 8,
  "active_streak": 14,
  "tracked_assets": 24,
  "updated_at": 1784800000,
  "country_code": "BE"
}
```

`country_code` is omitted unless the user explicitly enables it.

The client never includes market prices, symbols, alert messages, IP address, Wi-Fi/Bluetooth identifiers, wallet data, API keys or notification secrets.

## Recommended server response

Any 2xx JSON response is accepted. A future server can return:

```json
{
  "ok": true,
  "rank": 42,
  "total": 1200,
  "updated_at": 1784800001
}
```

## Server behavior

- Upsert by `device_id`.
- Reject unsupported `protocol_version` values with HTTP 400.
- When a token is issued, verify the Bearer token and HMAC signature.
- Apply a per-device/IP rate limit.
- Do not expose raw `device_id` values publicly; publish a separate server-side public identifier.
- Provide deletion/reset procedures for community participants.

## Client retry behavior

A successful sync follows the configured interval. A failed or unreachable server is retried no more than once every 15 minutes, preventing a future outage from consuming every market refresh cycle.
