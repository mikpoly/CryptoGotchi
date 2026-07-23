# Hotfix Technical Sentinel 500

This hotfix fixes an Internal Server Error triggered after pressing the companion analysis button.

Cause: support/resistance zones were stored as Python dataclass objects inside the worker status. The status snapshot is JSON-serialized, so the request failed with `TypeError: Object of type Zone is not JSON serializable`.

Fix: zones are now converted to plain dictionaries before being stored in the application status.

The warning for `bch` is unrelated. CoinGecko expects the ID `bitcoin-cash`, not `bch`.
