from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests

from . import __version__
from .config import ConfigManager
from .db import Database

log = logging.getLogger(__name__)


class NotifierHub:
    """Send private alerts and explicitly enabled public posts.

    Each integration follows the provider's documented HTTP endpoint. Errors are
    returned to the dashboard without ever logging configured tokens/passwords.
    """

    def __init__(self, config: ConfigManager, db: Database):
        self.config_manager = config
        self.db = db
        self.session = requests.Session()

    @staticmethod
    def format_message(alert: dict[str, Any], name: str, language: str = "en") -> str:
        disclaimer = (
            "Surveillance automatique, pas un conseil financier."
            if language == "fr"
            else "Automated monitoring, not financial advice."
        )
        return f"{alert['message']}\n\n{disclaimer}\n{name} by mikpoly\n#crypto #cryptogotchi"

    @staticmethod
    def _safe_https_url(value: str, label: str, allow_http_local: bool = False) -> str:
        url = str(value or "").strip().rstrip("/")
        parsed = urlparse(url)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if not parsed.netloc or parsed.scheme not in ({"http", "https"} if allow_http_local and local else {"https"}):
            raise ValueError(f"{label} must use a valid HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError(f"{label} must not contain credentials")
        return url

    @staticmethod
    def _response_error(response: Any) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = payload.get("error") or payload.get("message") or payload.get("detail")
                if message:
                    return str(message)[:240]
        except Exception:
            pass
        text = str(getattr(response, "text", "") or "").strip()
        return text[:240] or f"HTTP {getattr(response, 'status_code', '?')}"

    @classmethod
    def _raise_for_api(cls, response: Any, *, require_json_key: str | None = None) -> dict[str, Any]:
        response.raise_for_status()
        if require_json_key is None:
            try:
                data = response.json()
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        try:
            data = response.json()
        except Exception as exc:
            raise RuntimeError("Provider returned an invalid JSON response") from exc
        if not isinstance(data, dict) or not data.get(require_json_key):
            raise RuntimeError(cls._response_error(response))
        return data

    def dispatch(self, alert: dict[str, Any], test_only: str | None = None) -> list[dict[str, Any]]:
        cfg = self.config_manager.load()
        channels = cfg.get("notifications", {})
        name = cfg["main"].get("name", "CryptoGotchi")
        language = str(cfg.get("main", {}).get("language", "en"))
        message = self.format_message(alert, name, language)
        results: list[dict[str, Any]] = []
        if channels.get("paused") and not test_only:
            text = "External alerts are paused" if language == "en" else "Alertes externes en pause"
            return [{"channel": "all", "ok": False, "paused": True, "error": text}]

        private_handlers = {
            "telegram": self._telegram,
            "discord": self._discord,
            "webhook": self._webhook,
        }
        public_handlers = {
            "mastodon": self._mastodon,
            "bluesky": self._bluesky,
        }

        private_requested = bool(alert.get("private_notify", True)) or bool(test_only in private_handlers)
        for channel, handler in private_handlers.items():
            if test_only and channel != test_only:
                continue
            settings = channels.get(channel, {})
            if private_requested and settings.get("enabled"):
                results.append(self._safe_send(channel, handler, settings, message, alert))

        allow_public = bool(cfg.get("security", {}).get("allow_public_posts"))
        public_requested = bool(alert.get("social_post")) or bool(test_only in public_handlers)
        max_posts = int(cfg.get("security", {}).get("max_public_posts_per_hour", 3))
        for channel, handler in public_handlers.items():
            if test_only and channel != test_only:
                continue
            settings = channels.get(channel, {})
            if not settings.get("enabled"):
                continue
            if not allow_public:
                text = "Public posts are disabled" if language == "en" else "Publications publiques désactivées"
                results.append({"channel": channel, "ok": False, "error": text})
                continue
            if not public_requested:
                continue
            if not test_only and not self.db.can_public_post(max_posts):
                text = "Public post rate limit reached" if language == "en" else "Limite anti-spam atteinte"
                results.append({"channel": channel, "ok": False, "error": text})
                continue
            result = self._safe_send(channel, handler, settings, message, alert)
            results.append(result)
            if result["ok"] and not test_only:
                self.db.record_public_post(channel)
        return results

    @staticmethod
    def _redact_error(exc: Exception, settings: dict[str, Any]) -> str:
        """Return a useful provider error without leaking configured secrets."""
        text = str(exc) or exc.__class__.__name__
        secret_markers = ("token", "password", "secret", "webhook", "authorization")
        for key, raw in settings.items():
            value = str(raw or "").strip()
            if not value:
                continue
            key_lower = str(key).lower()
            if key_lower == "url" or any(marker in key_lower for marker in secret_markers):
                text = text.replace(value, "[redacted]")
        # Provider/client exceptions sometimes echo credentials embedded in URLs
        # even when the original request body is not logged.
        text = re.sub(r"bot[0-9]+:[A-Za-z0-9_-]+", "bot[redacted]", text)
        text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/=]+", r"\1[redacted]", text)
        return text[:240]

    def _safe_send(self, channel, handler, settings, message, alert):
        try:
            details = handler(settings, message, alert) or {}
            return {"channel": channel, "ok": True, **details}
        except Exception as exc:
            error = self._redact_error(exc, settings)
            log.warning("Notification %s failed: %s", channel, error)
            return {"channel": channel, "ok": False, "error": error}

    def _telegram(self, settings, message, alert):
        token = str(settings.get("bot_token", "")).strip()
        chat_id = str(settings.get("chat_id", "")).strip()
        if not token or not chat_id:
            raise ValueError("Telegram bot token or chat ID is missing")
        response = self.session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message[:4096],
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        data = self._raise_for_api(response)
        if data and data.get("ok") is False:
            raise RuntimeError(str(data.get("description") or "Telegram rejected the message")[:240])
        return {"provider_id": str((data.get("result") or {}).get("message_id", ""))} if data else {}

    def _discord(self, settings, message, alert):
        url = self._safe_https_url(settings.get("webhook_url", ""), "Discord webhook URL")
        response = self.session.post(
            url,
            params={"wait": "true"},
            json={
                "content": message[:2000],
                "username": "CryptoGotchi",
                "allowed_mentions": {"parse": []},
            },
            timeout=15,
        )
        data = self._raise_for_api(response)
        return {"provider_id": str(data.get("id", ""))} if data else {}

    def _mastodon(self, settings, message, alert):
        instance = self._safe_https_url(settings.get("instance_url", ""), "Mastodon instance")
        token = str(settings.get("access_token", "")).strip()
        if not token:
            raise ValueError("Mastodon access token is missing")
        visibility = str(settings.get("visibility", "unlisted"))
        if visibility not in {"public", "unlisted", "private", "direct"}:
            visibility = "unlisted"
        idempotency = hashlib.sha256(
            f"{alert.get('alert_key')}:{alert.get('ts')}:{message}".encode("utf-8")
        ).hexdigest()
        response = self.session.post(
            f"{instance}/api/v1/statuses",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": idempotency,
                "User-Agent": f"CryptoGotchi-by-mikpoly/{__version__}",
            },
            json={"status": message, "visibility": visibility},
            timeout=20,
        )
        data = self._raise_for_api(response)
        return {"provider_id": str(data.get("id", ""))} if data else {}

    def _bluesky(self, settings, message, alert):
        service = self._safe_https_url(settings.get("service_url", "https://bsky.social"), "Bluesky service")
        handle = str(settings.get("handle", "")).strip()
        password = str(settings.get("app_password", "")).strip()
        if not handle or not password:
            raise ValueError("Bluesky handle or App Password is missing")
        auth = self.session.post(
            f"{service}/xrpc/com.atproto.server.createSession",
            json={"identifier": handle, "password": password},
            timeout=20,
        )
        auth_data = self._raise_for_api(auth)
        did = str(auth_data.get("did") or "")
        token = str(auth_data.get("accessJwt") or "")
        if not did or not token:
            raise RuntimeError("Bluesky session response is missing did/accessJwt")
        created = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        body = {
            "repo": did,
            "collection": "app.bsky.feed.post",
            "record": {"$type": "app.bsky.feed.post", "text": message[:300], "createdAt": created},
        }
        response = self.session.post(
            f"{service}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=20,
        )
        data = self._raise_for_api(response)
        if data and not (data.get("uri") or data.get("cid")):
            raise RuntimeError("Bluesky did not return a record identifier")
        return {"provider_id": str(data.get("uri") or data.get("cid") or "")} if data else {}

    def _webhook(self, settings, message, alert):
        url = self._safe_https_url(settings.get("url", ""), "Webhook URL", allow_http_local=True)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"CryptoGotchi-by-mikpoly/{__version__}",
        }
        if settings.get("bearer_token"):
            headers["Authorization"] = f"Bearer {settings['bearer_token']}"
        response = self.session.post(
            url,
            headers=headers,
            json={
                "event": "cryptogotchi.alert",
                "schema_version": 1,
                "text": message,
                "alert": alert,
            },
            timeout=20,
        )
        self._raise_for_api(response)
        return {}
