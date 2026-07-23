from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any
from urllib.parse import urlparse

import requests

from . import __version__
from .config import ConfigManager
from .db import Database


class RankingClient:
    """Opt-in CryptoGotchi.world ranking client with per-device registration."""

    PROTOCOL_VERSION = 1
    DEFAULT_API_BASE = os.getenv("CRYPTOGOTCHI_RANKING_API", "https://cryptogotchi.world/api/v1").rstrip("/")

    def __init__(self, config: ConfigManager, db: Database):
        self.config_manager = config
        self.db = db
        self.session = requests.Session()

    def device_id(self) -> str:
        value = self.db.get_state("ranking:device_id", "")
        if isinstance(value, str) and len(value) >= 16:
            return value
        value = uuid.uuid4().hex
        self.db.set_state("ranking:device_id", value)
        return value

    def _api_base(self, section: dict[str, Any]) -> str:
        configured = str(section.get("endpoint_url") or "").strip()
        if not configured:
            return self.DEFAULT_API_BASE
        parsed = urlparse(configured)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("The ranking endpoint must be a valid HTTPS URL.")
        value = configured.rstrip("/")
        for suffix in ("/sync", "/register", "/cryptogotchi/ranking"):
            if value.endswith(suffix):
                value = value[: -len(suffix)]
                break
        return value

    def _token(self, section: dict[str, Any]) -> str:
        stored = self.db.get_state("ranking:device_token", "")
        if isinstance(stored, str) and stored:
            return stored
        legacy = str(section.get("api_token") or "").strip()
        return legacy

    def build_payload(self, status: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        config = config or self.config_manager.load()
        section = config.get("ranking", {})
        companion = status.get("companion", {}) or {}
        coins = status.get("coins", []) or []
        payload: dict[str, Any] = {
            "protocol_version": self.PROTOCOL_VERSION,
            "device_id": self.device_id(),
            "public_name": str(section.get("public_name") or config.get("main", {}).get("name") or "CryptoGotchi")[:40],
            "app_version": __version__,
            "level": int(companion.get("level", 1) or 1),
            "xp": int(companion.get("xp", 0) or 0),
            "observations": int(companion.get("observations", 0) or 0),
            "achievement_count": int(companion.get("achievement_count", 0) or 0),
            "active_streak": int(companion.get("active_streak", 0) or 0),
            "tracked_assets": len(coins),
            "updated_at": int(time.time()),
        }
        if bool(section.get("share_country")):
            code = str(section.get("country_code") or "").strip().upper()
            if len(code) == 2 and code.isalpha():
                payload["country_code"] = code
        return payload

    @staticmethod
    def _signature(body: bytes, token: str) -> str:
        return hmac.new(token.encode("utf-8"), body, hashlib.sha256).hexdigest()

    def _register(self, payload: dict[str, Any], section: dict[str, Any]) -> str:
        base = self._api_base(section)
        registration = {
            key: payload[key]
            for key in ("protocol_version", "device_id", "public_name", "app_version", "country_code")
            if key in payload
        }
        response = self.session.post(
            f"{base}/register",
            json=registration,
            headers={"Accept": "application/json", "User-Agent": f"CryptoGotchi-by-mikpoly/{__version__}"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        token = str(data.get("device_token") or "")
        if len(token) < 32:
            raise RuntimeError("The ranking server did not return a valid device token.")
        self.db.set_state("ranking:device_token", token)
        self.db.set_state("ranking:public_id", str(data.get("device_public_id") or ""))
        return token

    def status(self, current_status: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = self.config_manager.load()
        section = cfg.get("ranking", {})
        return {
            "enabled": bool(section.get("enabled")),
            "configured": True,
            "endpoint": self._api_base(section),
            "device_id": self.device_id(),
            "public_id": str(self.db.get_state("ranking:public_id", "") or ""),
            "registered": bool(self._token(section)),
            "last_sync_ts": int(self.db.get_state("ranking:last_sync_ts", 0) or 0),
            "last_attempt_ts": int(self.db.get_state("ranking:last_attempt_ts", 0) or 0),
            "last_error": str(self.db.get_state("ranking:last_error", "") or ""),
            "preview": self.build_payload(current_status or {}, cfg),
        }

    def should_sync(self, now: int | None = None) -> bool:
        cfg = self.config_manager.load()
        section = cfg.get("ranking", {})
        if not bool(section.get("enabled")):
            return False
        now = int(now or time.time())
        interval = max(1, min(168, int(section.get("sync_interval_hours", 6) or 6))) * 3600
        last_success = int(self.db.get_state("ranking:last_sync_ts", 0) or 0)
        last_attempt = int(self.db.get_state("ranking:last_attempt_ts", 0) or 0)
        last_error = str(self.db.get_state("ranking:last_error", "") or "")
        if last_error and last_attempt:
            return now - last_attempt >= min(interval, 15 * 60)
        return now - last_success >= interval and now - last_attempt >= 60

    def sync(self, status: dict[str, Any], force: bool = False) -> dict[str, Any]:
        cfg = self.config_manager.load()
        section = cfg.get("ranking", {})
        if not bool(section.get("enabled")):
            return {"ok": False, "skipped": True, "error": "Community ranking is disabled."}
        if not force and not self.should_sync():
            return {"ok": False, "skipped": True, "error": "Ranking sync is not due yet."}
        attempt_ts = int(time.time())
        self.db.set_state("ranking:last_attempt_ts", attempt_ts)
        try:
            payload = self.build_payload(status, cfg)
            token = self._token(section) or self._register(payload, section)
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "X-CryptoGotchi-Protocol": str(self.PROTOCOL_VERSION),
                "X-CryptoGotchi-Signature": self._signature(body, token),
                "User-Agent": f"CryptoGotchi-by-mikpoly/{__version__}",
            }
            response = self.session.post(f"{self._api_base(section)}/sync", data=body, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json() if response.content else {}
            now = int(time.time())
            self.db.set_state("ranking:last_sync_ts", now)
            self.db.set_state("ranking:last_error", "")
            return {"ok": True, "status_code": response.status_code, "response": data, "synced_at": now}
        except Exception as exc:
            error = str(exc)[:240]
            self.db.set_state("ranking:last_error", error)
            return {"ok": False, "error": error}
