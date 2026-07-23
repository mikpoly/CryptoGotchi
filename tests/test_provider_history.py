from cryptogotchi.config import default_config
from cryptogotchi.market import CoinGeckoProvider


class Response:
    content = b"123456"
    def raise_for_status(self):
        pass
    def json(self):
        return {
            "prices": [[1_700_000_000_000, 100.0], [1_700_000_300_000, 101.0]],
            "total_volumes": [[1_700_000_000_000, 500.0], [1_700_000_300_000, 550.0]],
        }


class Session:
    def get(self, *args, **kwargs):
        return Response()


def test_provider_parses_market_chart_and_counts_bytes():
    provider = CoinGeckoProvider(default_config())
    provider.session = Session()
    history = provider.fetch_history("bitcoin", "eur")
    assert history == [
        {"ts": 1_700_000_000, "price": 100.0, "volume": 500.0, "change_24h": None},
        {"ts": 1_700_000_300, "price": 101.0, "volume": 550.0, "change_24h": None},
    ]
    assert provider.consume_transfer_stats() == {"bytes": 6, "requests": 1}
