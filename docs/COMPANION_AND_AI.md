# Companion Life and optional AI

CryptoGotchi v0.7.0 has two narrative layers.

## Micro-Brain v2

The local brain is the default. It is deterministic enough for a Pi Zero 2 W but varies messages using market state, leading asset, volume, personality, recent phrases and persistent memory. Its data lives in the local SQLite database.

Life values are entertainment and interface state; they are not financial predictions.

## External AI

External generation is optional. Supported adapters:

- Ollama `/api/chat`
- OpenAI Responses API `/v1/responses`
- OpenAI-compatible `/v1/chat/completions`

The request contains only a compact market summary, a safe local draft and personality settings. CryptoGotchi explicitly instructs the model not to invent news, explanations, targets or trading advice.

When the server times out or returns an error, the local Micro-Brain remains available. External calls are disabled in data-saver mode unless the owner explicitly enables them.

## Editing the personality

Settings expose:

- archetype;
- humor;
- energy;
- prudence;
- technical level;
- talk frequency;
- optimism;
- verbosity;
- custom identity;
- optional extra system instructions.

The extra prompt should define tone, not ask the system to fabricate market causes or promise returns.
