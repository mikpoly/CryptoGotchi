# Market integrity and asset identity

CryptoGotchi v0.5 separates every price series with three keys:

```text
asset id + quote currency + provider
```

A BTC/EUR sample is never used to calculate BTC/USD performance. CoinGecko samples are never combined with Gold API samples. This prevents conversion-rate jumps from becoming fake crypto alerts.

## Tokenized assets

Some CoinGecko assets represent tokenized or synthetic exposure to a company. Their crypto-market token can trade 24/7 even when the traditional stock market is closed. CryptoGotchi labels these assets `tokenized_asset`, displays the 24/7 status, and excludes them from the broad crypto mood by default.

## Metal tickers

A crypto token can use symbols such as `XAU` without representing physical or spot gold. CryptoGotchi warns about those search results.

Use the dedicated **Real spot metals** buttons to add:

- XAU — Gold Spot
- XAG — Silver Spot
- XPT — Platinum Spot
- XPD — Palladium Spot
- HG — Copper Spot

Real-metal intraday history is built locally from fresh spot readings. Market-open/closed state is an estimated global session status and is displayed explicitly.

## Freshness

Each provider reading includes a data age. A stale or closed stream can still be displayed, but it cannot create threshold or broad-market alerts.
