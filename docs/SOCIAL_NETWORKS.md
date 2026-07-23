# Alerts and social networks

## Private channels

### Telegram

Enter a dedicated bot token and chat ID. CryptoGotchi uses the Bot API `sendMessage` endpoint, validates Telegram’s JSON result and limits text to the provider maximum. Run the Telegram test after saving.

### Discord

Enter a dedicated webhook URL. CryptoGotchi executes the webhook with confirmation enabled and disables automatic mentions in the payload. Run the Discord test after saving.

### Generic webhook

The webhook receives:

```json
{
  "event": "cryptogotchi.alert",
  "schema_version": 1,
  "text": "formatted alert",
  "alert": {}
}
```

HTTPS is required except for localhost development. An optional Bearer token can be configured.

## Public channels

Mastodon and Bluesky are blocked unless **I explicitly allow automatic posts** is checked. The global posts-per-hour limit and per-asset `social_post` setting are also enforced.

### Mastodon

CryptoGotchi posts JSON to `/api/v1/statuses`, uses the configured visibility, a Bearer token and an idempotency key so one alert is less likely to be duplicated.

### Bluesky

Use an App Password, never the main account password. CryptoGotchi creates a session and then an `app.bsky.feed.post` record limited to 300 characters.

## Verification limits

The automated test suite verifies request construction and error handling with mock HTTP sessions. A real provider account cannot be tested without the user’s private token, so always use each channel’s built-in test after installation.
