import time

from cryptogotchi.config import ConfigManager
from cryptogotchi.db import Database
from cryptogotchi.notifiers import NotifierHub


class FakeResponse:
    def __init__(self, data=None):
        self._data = data or {}
    def raise_for_status(self):
        return None
    def json(self):
        return self._data


class FakeSession:
    def __init__(self):
        self.calls = []
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("createSession"):
            return FakeResponse({"did": "did:plc:test", "accessJwt": "token"})
        return FakeResponse()


def alert(social=False):
    return {
        "alert_key": "test", "coin_id": "bitcoin", "symbol": "BTC",
        "rule": "drop_5m", "severity": "high", "message": "BTC baisse",
        "ts": int(time.time()), "metrics": {}, "social_post": social,
    }


def test_telegram_dispatch(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["notifications"]["telegram"].update({"enabled": True, "bot_token": "abc", "chat_id": "123"})
    manager.save(cfg)
    hub = NotifierHub(manager, Database(tmp_path / "db.sqlite"))
    hub.session = FakeSession()
    result = hub.dispatch(alert())
    assert result == [{"channel": "telegram", "ok": True}]
    assert "/botabc/sendMessage" in hub.session.calls[0][0]


def test_bluesky_requires_public_permission(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["notifications"]["bluesky"].update({"enabled": True, "handle": "test.bsky.social", "app_password": "app-pass"})
    manager.save(cfg)
    hub = NotifierHub(manager, Database(tmp_path / "db.sqlite"))
    hub.session = FakeSession()
    result = hub.dispatch(alert(social=True))
    assert result[0]["ok"] is False
    assert not hub.session.calls


def test_bluesky_public_post(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["security"]["allow_public_posts"] = True
    cfg["notifications"]["bluesky"].update({"enabled": True, "handle": "test.bsky.social", "app_password": "app-pass"})
    manager.save(cfg)
    hub = NotifierHub(manager, Database(tmp_path / "db.sqlite"))
    hub.session = FakeSession()
    result = hub.dispatch(alert(social=True))
    assert result == [{"channel": "bluesky", "ok": True}]
    assert len(hub.session.calls) == 2
    assert hub.session.calls[1][0].endswith("com.atproto.repo.createRecord")


def test_notifications_pause_blocks_external_calls(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["notifications"]["paused"] = True
    cfg["notifications"]["telegram"].update({"enabled": True, "bot_token": "abc", "chat_id": "123"})
    manager.save(cfg)
    hub = NotifierHub(manager, Database(tmp_path / "db.sqlite"))
    hub.session = FakeSession()
    result = hub.dispatch(alert())
    assert result[0]["paused"] is True
    assert hub.session.calls == []


def test_public_digest_can_skip_private_channels(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["security"]["allow_public_posts"] = True
    cfg["notifications"]["telegram"].update({"enabled": True, "bot_token": "abc", "chat_id": "123"})
    cfg["notifications"]["bluesky"].update({"enabled": True, "handle": "test.bsky.social", "app_password": "app-pass"})
    manager.save(cfg)
    hub = NotifierHub(manager, Database(tmp_path / "db.sqlite"))
    hub.session = FakeSession()
    digest = alert(social=True)
    digest["private_notify"] = False
    result = hub.dispatch(digest)
    assert result == [{"channel": "bluesky", "ok": True}]
    assert all("sendMessage" not in url for url, _ in hub.session.calls)


def test_discord_waits_for_confirmation_and_blocks_mentions(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["notifications"]["discord"].update({"enabled": True, "webhook_url": "https://discord.com/api/webhooks/1/token"})
    manager.save(cfg)
    hub = NotifierHub(manager, Database(tmp_path / "db.sqlite"))
    hub.session = FakeSession()
    result = hub.dispatch(alert())
    assert result[0]["ok"] is True
    _, kwargs = hub.session.calls[0]
    assert kwargs["params"] == {"wait": "true"}
    assert kwargs["json"]["allowed_mentions"] == {"parse": []}


def test_mastodon_uses_json_and_idempotency_key(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["security"]["allow_public_posts"] = True
    cfg["notifications"]["mastodon"].update({
        "enabled": True,
        "instance_url": "https://mastodon.example",
        "access_token": "token",
        "visibility": "unlisted",
    })
    manager.save(cfg)
    hub = NotifierHub(manager, Database(tmp_path / "db.sqlite"))
    hub.session = FakeSession()
    result = hub.dispatch(alert(social=True))
    assert result[0]["ok"] is True
    url, kwargs = hub.session.calls[0]
    assert url.endswith("/api/v1/statuses")
    assert kwargs["json"]["visibility"] == "unlisted"
    assert "Idempotency-Key" in kwargs["headers"]


def test_webhook_rejects_plain_http_remote_url(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    cfg = manager.load()
    cfg["notifications"]["webhook"].update({"enabled": True, "url": "http://example.org/hook"})
    manager.save(cfg)
    hub = NotifierHub(manager, Database(tmp_path / "db.sqlite"))
    hub.session = FakeSession()
    result = hub.dispatch(alert())
    assert result[0]["ok"] is False
    assert "HTTPS" in result[0]["error"]
    assert hub.session.calls == []


def test_safe_send_redacts_secrets(tmp_path):
    manager = ConfigManager(tmp_path / "config.toml")
    hub = NotifierHub(manager, Database(tmp_path / "db.sqlite"))
    secret = "123456:VERY_SECRET_TOKEN"

    def failing(settings, message, alert):
        raise RuntimeError(f"request failed at https://api.telegram.org/bot{secret}/sendMessage Bearer {secret}")

    result = hub._safe_send(
        "telegram",
        failing,
        {"bot_token": secret, "chat_id": "42"},
        "message",
        {},
    )
    assert result["ok"] is False
    assert secret not in result["error"]
    assert "redacted" in result["error"]

    webhook = "https://hooks.example/private/path-token"
    webhook_error = hub._redact_error(RuntimeError(f"connection failed for {webhook}"), {"url": webhook})
    assert webhook not in webhook_error
