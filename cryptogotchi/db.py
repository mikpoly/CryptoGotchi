from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS price_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coin_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    price REAL NOT NULL,
    volume REAL,
    change_24h REAL,
    quote_currency TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'coingecko'
);
-- The stream index is created only after the legacy-table migration.
-- Existing databases from v0.4 and earlier do not yet have quote_currency/source,
-- and SQLite would otherwise fail before the migration can add them.

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_key TEXT NOT NULL,
    coin_id TEXT,
    rule TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT,
    ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alert_key_ts ON alerts(alert_key, ts);

CREATE TABLE IF NOT EXISTS public_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kv_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    language TEXT NOT NULL,
    text TEXT NOT NULL,
    payload_json TEXT,
    ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_journal_day_ts ON journal_entries(day, ts);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state_lock = threading.RLock()
        with self.connect() as conn:
            # Create tables first, migrate legacy columns second, then create
            # indexes that depend on the new columns. This order is critical
            # when upgrading an existing CryptoGotchi database.
            conn.executescript(SCHEMA)
            self._migrate_price_samples(conn)

    @staticmethod
    def _migrate_price_samples(conn: sqlite3.Connection) -> None:
        """Migrate databases created before v0.5 without losing user data.

        Old samples have no quote/source metadata. They are intentionally left
        with an empty quote so they cannot be mixed with USD/EUR samples. This
        prevents false +10–20% moves after changing the display currency.
        """
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(price_samples)").fetchall()}
        if "quote_currency" not in columns:
            conn.execute("ALTER TABLE price_samples ADD COLUMN quote_currency TEXT NOT NULL DEFAULT ''")
        if "source" not in columns:
            conn.execute("ALTER TABLE price_samples ADD COLUMN source TEXT NOT NULL DEFAULT 'coingecko'")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_price_coin_quote_source_ts "
            "ON price_samples(coin_id, quote_currency, source, ts)"
        )

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=20)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _quote(value: str | None) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _source(value: str | None) -> str:
        return str(value or "coingecko").strip().lower()

    def add_sample(
        self,
        coin_id: str,
        ts: int,
        price: float,
        volume: float | None,
        change_24h: float | None,
        quote_currency: str = "",
        source: str = "coingecko",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO price_samples(coin_id, ts, price, volume, change_24h, quote_currency, source) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    coin_id,
                    ts,
                    price,
                    volume,
                    change_24h,
                    self._quote(quote_currency),
                    self._source(source),
                ),
            )

    def add_samples(
        self,
        coin_id: str,
        samples: Iterable[dict[str, Any]],
        quote_currency: str = "",
        source: str = "coingecko",
    ) -> int:
        """Add history while avoiding duplicate timestamps for one data stream."""
        quote = self._quote(quote_currency)
        provider = self._source(source)
        rows: list[tuple[str, int, float, float | None, float | None, str, str]] = []
        for sample in samples:
            try:
                ts = int(sample["ts"])
                price = float(sample["price"])
            except (KeyError, TypeError, ValueError):
                continue
            volume = sample.get("volume")
            rows.append(
                (
                    coin_id,
                    ts,
                    price,
                    float(volume) if volume is not None else None,
                    sample.get("change_24h"),
                    quote,
                    provider,
                )
            )
        if not rows:
            return 0
        inserted = 0
        with self.connect() as conn:
            for row in rows:
                exists = conn.execute(
                    "SELECT 1 FROM price_samples WHERE coin_id=? AND ts=? AND quote_currency=? AND source=? LIMIT 1",
                    (row[0], row[1], row[5], row[6]),
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT INTO price_samples(coin_id, ts, price, volume, change_24h, quote_currency, source) "
                    "VALUES(?,?,?,?,?,?,?)",
                    row,
                )
                inserted += 1
        return inserted

    def reference_sample(
        self,
        coin_id: str,
        target_ts: int,
        quote_currency: str = "",
        source: str = "coingecko",
        max_age_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        quote = self._quote(quote_currency)
        provider = self._source(source)
        params: list[Any] = [coin_id, quote, provider, target_ts]
        extra = ""
        if max_age_seconds is not None:
            extra = " AND ts>=?"
            params.append(target_ts - max(1, int(max_age_seconds)))
        with self.connect() as conn:
            row = conn.execute(
                "SELECT ts, price, volume, quote_currency, source FROM price_samples "
                "WHERE coin_id=? AND quote_currency=? AND source=? AND ts<=?" + extra +
                " ORDER BY ts DESC LIMIT 1",
                params,
            ).fetchone()
        return dict(row) if row else None

    def samples_since(
        self,
        coin_id: str,
        since_ts: int,
        exclude_latest: bool = False,
        quote_currency: str = "",
        source: str = "coingecko",
    ) -> list[dict[str, Any]]:
        quote = self._quote(quote_currency)
        provider = self._source(source)
        sql = (
            "SELECT ts, price, volume, change_24h, quote_currency, source FROM price_samples "
            "WHERE coin_id=? AND quote_currency=? AND source=? AND ts>=? ORDER BY ts ASC"
        )
        with self.connect() as conn:
            rows = conn.execute(sql, (coin_id, quote, provider, since_ts)).fetchall()
        data = [dict(r) for r in rows]
        return data[:-1] if exclude_latest and data else data

    def sample_count(
        self,
        coin_id: str,
        since_ts: int | None = None,
        quote_currency: str = "",
        source: str = "coingecko",
    ) -> int:
        quote = self._quote(quote_currency)
        provider = self._source(source)
        with self.connect() as conn:
            if since_ts is None:
                row = conn.execute(
                    "SELECT COUNT(*) FROM price_samples WHERE coin_id=? AND quote_currency=? AND source=?",
                    (coin_id, quote, provider),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM price_samples WHERE coin_id=? AND quote_currency=? AND source=? AND ts>=?",
                    (coin_id, quote, provider, since_ts),
                ).fetchone()
        return int(row[0] if row else 0)

    def latest_samples(self, quote_currency: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if quote_currency is None:
                rows = conn.execute(
                    """
                    SELECT p.coin_id, p.ts, p.price, p.volume, p.change_24h, p.quote_currency, p.source
                    FROM price_samples p
                    JOIN (
                        SELECT coin_id, quote_currency, source, MAX(ts) ts
                        FROM price_samples GROUP BY coin_id, quote_currency, source
                    ) x ON x.coin_id=p.coin_id AND x.quote_currency=p.quote_currency
                       AND x.source=p.source AND x.ts=p.ts
                    ORDER BY p.coin_id
                    """
                ).fetchall()
            else:
                quote = self._quote(quote_currency)
                rows = conn.execute(
                    """
                    SELECT p.coin_id, p.ts, p.price, p.volume, p.change_24h, p.quote_currency, p.source
                    FROM price_samples p
                    JOIN (
                        SELECT coin_id, quote_currency, source, MAX(ts) ts
                        FROM price_samples WHERE quote_currency=?
                        GROUP BY coin_id, quote_currency, source
                    ) x ON x.coin_id=p.coin_id AND x.quote_currency=p.quote_currency
                       AND x.source=p.source AND x.ts=p.ts
                    ORDER BY p.coin_id
                    """,
                    (quote,),
                ).fetchall()
        return [dict(r) for r in rows]

    def delete_samples(self, coin_id: str, quote_currency: str | None = None, source: str | None = None) -> int:
        clauses = ["coin_id=?"]
        params: list[Any] = [coin_id]
        if quote_currency is not None:
            clauses.append("quote_currency=?")
            params.append(self._quote(quote_currency))
        if source is not None:
            clauses.append("source=?")
            params.append(self._source(source))
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM price_samples WHERE " + " AND ".join(clauses), params)
            return int(cursor.rowcount or 0)

    def recent_alert_exists(self, alert_key: str, since_ts: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM alerts WHERE alert_key=? AND ts>=? LIMIT 1",
                (alert_key, since_ts),
            ).fetchone()
        return bool(row)

    def record_alert(self, alert: dict[str, Any], payload_json: str = "") -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO alerts(alert_key, coin_id, rule, severity, message, payload_json, ts) VALUES(?,?,?,?,?,?,?)",
                (
                    alert["alert_key"], alert.get("coin_id"), alert["rule"], alert["severity"],
                    alert["message"], payload_json, alert["ts"],
                ),
            )
            return int(cursor.lastrowid)

    def latest_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, coin_id, rule, severity, message, ts FROM alerts ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_price_samples(self) -> int:
        """Remove market samples while preserving configuration and companion state."""
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM price_samples")
            return int(cursor.rowcount or 0)

    def clear_alerts(self) -> int:
        """Clear alert rows after a market-integrity migration."""
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM alerts")
            return int(cursor.rowcount or 0)

    def clear_journals(self) -> int:
        """Remove market-derived journal entries without resetting companion XP."""
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM journal_entries")
            return int(cursor.rowcount or 0)

    def can_public_post(self, max_per_hour: int) -> bool:
        if max_per_hour <= 0:
            return False
        since = int(time.time()) - 3600
        with self.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM public_posts WHERE ts>=?", (since,)).fetchone()[0]
        return count < max_per_hour

    def record_public_post(self, channel: str) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO public_posts(channel, ts) VALUES(?,?)", (channel, int(time.time())))

    def get_state(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM kv_state WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return row[0]

    def set_state(self, key: str, value: Any) -> None:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO kv_state(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, encoded),
            )

    def add_journal_entry(self, day: str, language: str, text: str, payload: dict[str, Any] | None = None) -> int:
        encoded = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))
        now = int(time.time())
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM journal_entries WHERE day=? AND language=? AND text=? ORDER BY id DESC LIMIT 1",
                (day, language, text),
            ).fetchone()
            if existing:
                return int(existing[0])
            cursor = conn.execute(
                "INSERT INTO journal_entries(day, language, text, payload_json, ts) VALUES(?,?,?,?,?)",
                (day, language, text, encoded, now),
            )
            return int(cursor.lastrowid)

    def latest_journal_entries(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, day, language, text, payload_json, ts FROM journal_entries ORDER BY ts DESC, id DESC LIMIT ?",
                (max(1, min(365, int(limit))),),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.pop("payload_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                item["payload"] = {}
            result.append(item)
        return result

    def add_network_usage(self, byte_count: int, request_count: int = 1, now: int | None = None) -> dict[str, int]:
        now = int(now or time.time())
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        key = f"network_usage:{day}"
        with self._state_lock:
            state = self.get_state(key, {"bytes": 0, "requests": 0, "first_ts": now})
            if not isinstance(state, dict):
                state = {"bytes": 0, "requests": 0, "first_ts": now}
            state["bytes"] = max(0, int(state.get("bytes", 0))) + max(0, int(byte_count))
            state["requests"] = max(0, int(state.get("requests", 0))) + max(0, int(request_count))
            state["first_ts"] = int(state.get("first_ts") or now)
            self.set_state(key, state)
            return {"bytes": int(state["bytes"]), "requests": int(state["requests"]), "first_ts": int(state["first_ts"])}

    def network_usage_today(self, now: int | None = None) -> dict[str, int]:
        now = int(now or time.time())
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        state = self.get_state(f"network_usage:{day}", {"bytes": 0, "requests": 0, "first_ts": now})
        if not isinstance(state, dict):
            state = {"bytes": 0, "requests": 0, "first_ts": now}
        return {
            "bytes": int(state.get("bytes", 0) or 0),
            "requests": int(state.get("requests", 0) or 0),
            "first_ts": int(state.get("first_ts", now) or now),
        }

    def prune(self, history_hours: int) -> None:
        cutoff = int(time.time()) - max(2, history_hours) * 3600
        old_alerts = int(time.time()) - 30 * 86400
        with self.connect() as conn:
            conn.execute("DELETE FROM price_samples WHERE ts<?", (cutoff,))
            conn.execute("DELETE FROM alerts WHERE ts<?", (old_alerts,))
            conn.execute("DELETE FROM public_posts WHERE ts<?", (old_alerts,))
            conn.execute("DELETE FROM journal_entries WHERE ts<?", (int(time.time()) - 365 * 86400,))
            keys = conn.execute("SELECT key FROM kv_state WHERE key LIKE 'network_usage:%'").fetchall()
            for row in keys:
                try:
                    day = str(row[0]).split(":", 1)[1]
                    parsed = time.mktime(time.strptime(day, "%Y-%m-%d"))
                except (IndexError, ValueError, OverflowError):
                    continue
                if parsed < old_alerts:
                    conn.execute("DELETE FROM kv_state WHERE key=?", (row[0],))
        try:
            with self.connect() as conn:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.OperationalError:
            pass
