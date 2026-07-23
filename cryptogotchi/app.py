from __future__ import annotations

import logging
import os
import secrets
import signal
import subprocess
import time
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .config import COIN_DEFAULTS, ConfigManager, asset_data_note
from .connectivity import BluetoothManager, active_connection_info
from .db import Database
from .i18n import SUPPORTED_LANGUAGES, normalize_language, translate
from .market import HARD_MAX_ACTIVE_ASSETS, VERSION, CoinGeckoProvider, MarketWorker
from .wifi import build_wifi_profile_commands


def _bool(name: str) -> bool:
    return request.form.get(name) == "on"


def _float(name: str, default: float = 0.0) -> float:
    try:
        return float(request.form.get(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int = 0) -> int:
    try:
        return int(request.form.get(name, default))
    except (TypeError, ValueError):
        return default


def create_app(config_path: str | None = None, data_dir: str | None = None, start_worker: bool = False) -> Flask:
    config_path = config_path or os.environ.get("CRYPTOGOTCHI_CONFIG", "/etc/cryptogotchi/config.toml")
    data_dir = data_dir or os.environ.get("CRYPTOGOTCHI_DATA_DIR", "/var/lib/cryptogotchi")
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    config_manager = ConfigManager(config_path)
    cfg = config_manager.load()
    db = Database(Path(data_dir) / "cryptogotchi.db")
    worker = MarketWorker(config_manager, db)
    bluetooth = BluetoothManager()

    app = Flask(__name__)
    app.secret_key = cfg["security"]["secret_key"]
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    app.extensions.update({
        "cryptogotchi_config": config_manager,
        "cryptogotchi_db": db,
        "cryptogotchi_worker": worker,
        "cryptogotchi_bluetooth": bluetooth,
    })

    def language() -> str:
        return normalize_language(config_manager.load().get("main", {}).get("language", "en"))

    def tr(key: str, **values: Any) -> str:
        return translate(key, language(), **values)

    def branding_logo_path() -> Path | None:
        current = config_manager.load()
        raw = str(current.get("branding", {}).get("logo_path") or current.get("main", {}).get("logo_path") or "logo.png").strip()
        candidates: list[Path] = []
        raw_path = Path(raw)
        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            candidates.extend([
                Path(config_path).parent / raw,
                Path(data_dir) / raw,
                Path.cwd() / raw,
            ])
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def csrf_token() -> str:
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(24)
        return session["csrf_token"]

    @app.context_processor
    def template_context():
        current = config_manager.load()
        lang = normalize_language(current.get("main", {}).get("language", "en"))
        logo_exists = branding_logo_path() is not None
        return {
            "app_name": current["main"].get("name", "CryptoGotchi"),
            "csrf_token": csrf_token,
            "now": int(time.time()),
            "language": lang,
            "t": lambda key, **values: translate(key, lang, **values),
            "version": VERSION,
            "branding_logo_url": url_for("branding_logo") if logo_exists else "",
            "branding_logo_enabled": logo_exists,
        }

    @app.before_request
    def protect_csrf():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not supplied or not secrets.compare_digest(str(supplied), str(session.get("csrf_token", ""))):
                abort(400, "Invalid CSRF token" if language() == "en" else "Jeton CSRF invalide")

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
        )
        if request.endpoint != "health":
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def is_configured() -> bool:
        return bool(config_manager.load().get("security", {}).get("password_hash"))

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not is_configured():
                return redirect(url_for("setup"))
            if not session.get("authenticated"):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if is_configured():
            return redirect(url_for("login"))
        if request.method == "POST":
            username = request.form.get("username", "admin").strip() or "admin"
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")
            if len(password) < 10:
                flash(tr("flash.password_short"), "error")
            elif password != confirm:
                flash(tr("flash.password_mismatch"), "error")
            else:
                def update(current):
                    current["security"]["username"] = username
                    current["security"]["password_hash"] = generate_password_hash(password)
                config_manager.update(update)
                session["authenticated"] = True
                csrf_token()
                worker.display.wake()
                flash(tr("flash.setup_done"), "success")
                return redirect(url_for("dashboard"))
        return render_template("setup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not is_configured():
            return redirect(url_for("setup"))
        if request.method == "POST":
            current = config_manager.load()
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            if username == current["security"].get("username") and check_password_hash(current["security"].get("password_hash", ""), password):
                session.clear()
                session["authenticated"] = True
                csrf_token()
                worker.display.wake()
                next_url = request.args.get("next", "")
                if not next_url.startswith("/") or next_url.startswith("//"):
                    next_url = url_for("dashboard")
                return redirect(next_url)
            flash(tr("flash.bad_login"), "error")
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/branding/logo")
    def branding_logo():
        logo = branding_logo_path()
        if not logo:
            abort(404)
        return send_file(logo)

    @app.get("/")
    @login_required
    def dashboard():
        return render_template("dashboard.html", status=worker.status(), alerts=db.latest_alerts(25))

    @app.get("/companion")
    @login_required
    def companion():
        current = config_manager.load()
        lang = normalize_language(current["main"].get("language", "en"))
        status = worker.status()
        companion_status = {**worker.brain.snapshot(lang, current.get("personality", {})), **(status.get("companion") or {})}
        return render_template(
            "companion.html",
            status=status,
            companion=companion_status,
            achievements=worker.brain.achievement_details(lang),
            journals=worker.brain.journals(30),
            selected_coins=worker.selected_coins_status(),
        )

    @app.get("/analysis")
    @login_required
    def analysis():
        current = config_manager.load()
        status = worker.status()
        companion_status = status.get("companion") or {}
        analysis_cards = companion_status.get("technical_analysis") or worker.selected_coin_analyses()
        return render_template(
            "analysis.html",
            status=status,
            analysis_cards=analysis_cards,
            selected_coins=worker.selected_coins_status(),
            selected_coin_ids=worker.companion_selected_ids(),
            available_coins=status.get("coins", []),
            cfg=current,
        )

    @app.post("/analysis/run")
    @login_required
    def analysis_run():
        selected = request.form.getlist("coin_ids")
        try:
            worker.ask_selected_coins(selected if selected else None)
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("analysis"))

    @app.post("/companion/interact/<action>")
    @login_required
    def companion_interact(action: str):
        if action not in {"pet", "encourage", "rest"}:
            abort(404)
        worker.interact(action)
        return redirect(url_for("companion"))

    @app.post("/companion/ask")
    @login_required
    def companion_ask():
        # Backward-compatible endpoint kept for bookmarks/forms from v0.7.1.
        selected = request.form.getlist("coin_ids")
        try:
            worker.ask_selected_coins(selected if selected else None)
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("analysis"))

    @app.post("/companion/journal")
    @login_required
    def companion_journal():
        entry = worker.create_journal_now()
        flash(tr("flash.journal_created") if entry else tr("flash.journal_unavailable"), "success" if entry else "error")
        return redirect(url_for("companion"))

    @app.get("/coins")
    @login_required
    def coins():
        current = config_manager.load()
        lang = normalize_language(current.get("main", {}).get("language", "en"))
        display_coins = []
        for coin in current.get("coins", []):
            item = dict(coin)
            item["data_note"] = asset_data_note(coin, lang)
            display_coins.append(item)
        active_count = sum(1 for coin in current.get("coins", []) if coin.get("enabled", True))
        return render_template("coins.html", coins=display_coins, active_count=active_count, active_limit=worker.active_asset_limit(current))

    @app.post("/coins/add")
    @login_required
    def add_coin():
        coin_id = request.form.get("coin_id", "").strip().lower()
        if not coin_id:
            flash(tr("flash.coin_required"), "error")
            return redirect(url_for("coins"))

        metadata: dict[str, Any] = {
            "id": coin_id,
            "symbol": request.form.get("symbol", coin_id[:6]).strip().upper(),
            "name": request.form.get("name", coin_id).strip(),
            "asset_kind": request.form.get("asset_kind", "crypto").strip().lower() or "crypto",
            "trading_mode": "24x7",
            "data_note": request.form.get("data_note", "").strip(),
            "include_in_market_mood": True,
        }
        try:
            metadata.update(CoinGeckoProvider(config_manager.load()).inspect_coin(coin_id))
        except Exception as exc:
            logging.getLogger(__name__).warning("Coin metadata unavailable for %s: %s", coin_id, exc)
        if metadata.get("asset_kind") in {"tokenized_asset", "crypto_token"}:
            metadata["include_in_market_mood"] = False

        def update(current):
            if any(c["id"] == coin_id for c in current.get("coins", [])):
                raise ValueError(tr("flash.coin_exists"))
            active_limit = MarketWorker.active_asset_limit(current)
            active_count = sum(1 for item in current.get("coins", []) if item.get("enabled", True))
            if active_count >= active_limit:
                raise ValueError(tr("flash.active_limit", limit=active_limit))
            current.setdefault("coins", []).append({
                **COIN_DEFAULTS,
                "id": coin_id,
                "symbol": str(metadata.get("symbol") or coin_id[:6]).upper(),
                "name": str(metadata.get("name") or coin_id),
                "source": "coingecko",
                "asset_kind": metadata.get("asset_kind", "crypto"),
                "trading_mode": metadata.get("trading_mode", "24x7"),
                "data_note": metadata.get("data_note", ""),
                "include_in_market_mood": bool(metadata.get("include_in_market_mood", True)),
                "alerts_enabled": _bool("alerts_enabled") if metadata.get("asset_kind") not in {"tokenized_asset", "crypto_token"} else False,
                "drop_5m": abs(_float("drop_5m", 2)), "rise_5m": abs(_float("rise_5m", 2)),
                "drop_15m": abs(_float("drop_15m", 3)), "rise_15m": abs(_float("rise_15m", 3)),
                "drop_1h": abs(_float("drop_1h", 5)), "rise_1h": abs(_float("rise_1h", 5)),
                "drop_24h": abs(_float("drop_24h", 10)), "rise_24h": abs(_float("rise_24h", 10)),
                "volume_multiplier": max(0, _float("volume_multiplier", 2.5)),
                "cooldown_minutes": max(1, _int("cooldown_minutes", 30)),
                "social_post": _bool("social_post"),
                "favorite": _bool("favorite"),
            })
        try:
            config_manager.update(update)
            worker.request_backfill(coin_id)
            note = str(metadata.get("data_note") or "")
            flash(tr("flash.coin_added", coin=coin_id) + (f" — {note}" if note else ""), "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("coins"))

    @app.post("/coins/add-metal")
    @login_required
    def add_metal():
        symbol = request.form.get("metal_symbol", "XAU").strip().upper()
        supported = {"XAU": "Gold Spot", "XAG": "Silver Spot", "XPT": "Platinum Spot", "XPD": "Palladium Spot", "HG": "Copper Spot"}
        if symbol not in supported:
            abort(400, "Unsupported metal")
        coin_id = f"spot-{symbol.lower()}"

        def update(current):
            if any(c["id"] == coin_id for c in current.get("coins", [])):
                raise ValueError(tr("flash.coin_exists"))
            active_limit = MarketWorker.active_asset_limit(current)
            active_count = sum(1 for item in current.get("coins", []) if item.get("enabled", True))
            if active_count >= active_limit:
                raise ValueError(tr("flash.active_limit", limit=active_limit))
            current.setdefault("coins", []).append({
                **COIN_DEFAULTS,
                "id": coin_id,
                "symbol": symbol,
                "provider_symbol": symbol,
                "name": supported[symbol],
                "source": "gold_api",
                "asset_kind": "commodity",
                "trading_mode": "market_session",
                "data_note": "Spot metal per troy ounce from Gold API; intraday history is built locally.",
                "include_in_market_mood": False,
                "volume_multiplier": 0.0,
                "new_high_24h": False,
                "new_low_24h": False,
            })
        try:
            config_manager.update(update)
            worker.force_refresh()
            flash(tr("flash.coin_added", coin=symbol), "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("coins"))

    @app.post("/coins/<coin_id>/update")
    @login_required
    def update_coin(coin_id: str):
        def update(current):
            coin = next((c for c in current.get("coins", []) if c["id"] == coin_id), None)
            if not coin:
                raise ValueError(tr("flash.coin_missing"))
            wants_enabled = _bool("enabled")
            if wants_enabled and not coin.get("enabled", True):
                active_limit = MarketWorker.active_asset_limit(current)
                active_count = sum(1 for item in current.get("coins", []) if item.get("enabled", True))
                if active_count >= active_limit:
                    raise ValueError(tr("flash.active_limit", limit=active_limit))
            coin.update({
                "symbol": request.form.get("symbol", coin.get("symbol", "")).strip().upper(),
                "name": request.form.get("name", coin.get("name", "")).strip(),
                "enabled": wants_enabled, "alerts_enabled": _bool("alerts_enabled"), "favorite": _bool("favorite"),
                "include_in_market_mood": _bool("include_in_market_mood"),
                "drop_5m": abs(_float("drop_5m", 0)), "rise_5m": abs(_float("rise_5m", 0)),
                "drop_15m": abs(_float("drop_15m", 0)), "rise_15m": abs(_float("rise_15m", 0)),
                "drop_1h": abs(_float("drop_1h", 0)), "rise_1h": abs(_float("rise_1h", 0)),
                "drop_24h": abs(_float("drop_24h", 0)), "rise_24h": abs(_float("rise_24h", 0)),
                "volume_multiplier": max(0, _float("volume_multiplier", 0)),
                "new_high_24h": _bool("new_high_24h"), "new_low_24h": _bool("new_low_24h"),
                "cooldown_minutes": max(1, _int("cooldown_minutes", 30)),
                "social_post": _bool("social_post"),
            })
        try:
            config_manager.update(update)
            flash(tr("flash.rules_saved"), "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("coins"))

    @app.post("/coins/<coin_id>/history")
    @login_required
    def rebuild_coin_history(coin_id: str):
        if not any(c.get("id") == coin_id for c in config_manager.load().get("coins", [])):
            abort(404)
        worker.request_backfill(coin_id)
        flash(tr("flash.history_requested"), "success")
        return redirect(url_for("coins"))

    @app.post("/coins/<coin_id>/delete")
    @login_required
    def delete_coin(coin_id: str):
        config_manager.update(lambda current: current.update({"coins": [c for c in current.get("coins", []) if c["id"] != coin_id]}))
        db.delete_samples(coin_id)
        flash(tr("flash.coin_deleted"), "success")
        return redirect(url_for("coins"))

    def split_nmcli_line(line: str) -> list[str]:
        fields, current, escaped = [], [], False
        for char in line:
            if escaped:
                current.append(char); escaped = False
            elif char == "\\":
                escaped = True
            elif char == ":":
                fields.append("".join(current)); current = []
            else:
                current.append(char)
        fields.append("".join(current))
        return fields

    @app.get("/api/wifi/scan")
    @login_required
    def wifi_scan():
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"],
                capture_output=True, text=True, timeout=30, check=True,
            )
            networks, seen = [], set()
            for line in result.stdout.splitlines():
                parts = split_nmcli_line(line)
                if len(parts) < 3 or not parts[0] or parts[0] in seen:
                    continue
                seen.add(parts[0])
                networks.append({"ssid": parts[0], "signal": parts[1], "security": parts[2]})
            networks.sort(key=lambda item: int(item["signal"] or 0), reverse=True)
            return jsonify(networks[:30])
        except FileNotFoundError:
            return jsonify({"error": "NetworkManager/nmcli is not installed"}), 503
        except Exception as exc:
            return jsonify({"error": str(exc)[:200]}), 502

    @app.post("/wifi/connect")
    @login_required
    def wifi_connect():
        ssid = request.form.get("wifi_ssid", "").strip()
        password = request.form.get("wifi_password", "")
        hidden = _bool("wifi_hidden")
        security = request.form.get("wifi_security", "wpa-psk").strip().lower()
        lang = language()
        if not ssid or len(ssid.encode("utf-8")) > 32 or ssid.startswith("-") or any(c in ssid for c in "\r\n\x00"):
            flash("Invalid Wi-Fi name (32 bytes maximum)." if lang == "en" else "Nom Wi-Fi invalide (32 octets maximum).", "error")
            return redirect(url_for("settings"))
        if security not in {"wpa-psk", "sae", "open"}:
            flash("Invalid Wi-Fi security type." if lang == "en" else "Type de sécurité Wi-Fi invalide.", "error")
            return redirect(url_for("settings"))
        if security != "open" and not password:
            flash("A password is required for a protected network." if lang == "en" else "Le mot de passe Wi-Fi est obligatoire pour un réseau protégé.", "error")
            return redirect(url_for("settings"))
        commands = build_wifi_profile_commands(ssid, password, hidden, security)
        try:
            for index, (arguments, timeout) in enumerate(commands):
                result = subprocess.run(
                    ["nmcli", "--wait", str(max(10, timeout - 5)), *arguments],
                    capture_output=True, text=True, timeout=timeout, check=False,
                )
                if index and result.returncode != 0:
                    raise RuntimeError((result.stderr or result.stdout or "NetworkManager error").strip())
            worker.display.wake()
            flash(tr("flash.wifi_connected", ssid=ssid), "success")
        except FileNotFoundError:
            flash("NetworkManager/nmcli is not installed.", "error")
        except Exception as exc:
            flash(f"Wi-Fi error: {str(exc)[:240]}", "error")
        return redirect(url_for("settings"))

    @app.post("/wifi/power/<state>")
    @login_required
    def wifi_power(state: str):
        if state not in {"on", "off"}:
            abort(404)
        enabled = state == "on"
        try:
            details = bluetooth.set_wifi_enabled(enabled)
            message = (
                "Wi-Fi activé. Le Bluetooth n’a pas été modifié."
                if enabled and language() == "fr" else
                "Désactivation du Wi-Fi programmée. Le garde-fou le réactivera si le Bluetooth PAN disparaît."
                if not enabled and language() == "fr" else
                "Wi-Fi enabled. Bluetooth was not changed."
                if enabled else
                "Wi-Fi disable scheduled. The safety watchdog will restore it if Bluetooth PAN disappears."
            )
            flash(message + (f" ({details})" if details else ""), "success")
        except Exception as exc:
            flash(f"Wi-Fi power error: {str(exc)[:500]}", "error")
        return redirect(url_for("settings"))

    @app.post("/bluetooth/power/<state>")
    @login_required
    def bluetooth_power(state: str):
        if state not in {"on", "off"}:
            abort(404)
        enabled = state == "on"
        try:
            details = bluetooth.set_enabled(enabled)
            def update(current):
                current.setdefault("connectivity", {})["bluetooth_enabled"] = enabled
            config_manager.update(update)
            message = (
                "Bluetooth activé. Le Wi-Fi n’a pas été modifié."
                if enabled and language() == "fr" else
                "Bluetooth désactivé. Le Wi-Fi n’a pas été modifié."
                if not enabled and language() == "fr" else
                "Bluetooth enabled. Wi-Fi was not changed."
                if enabled else
                "Bluetooth disabled. Wi-Fi was not changed."
            )
            flash(message + (f" ({details})" if details else ""), "success")
        except Exception as exc:
            flash(f"Bluetooth power error: {str(exc)[:300]}", "error")
        return redirect(url_for("settings"))

    @app.post("/bluetooth/prepare")
    @login_required
    def bluetooth_prepare():
        try:
            message = bluetooth.prepare_pairing()
            flash(message or tr("flash.bluetooth_pairing_mode"), "success")
        except Exception as exc:
            flash(f"Bluetooth pairing mode error: {str(exc)[:500]}", "error")
        return redirect(url_for("settings"))

    @app.get("/api/bluetooth/scan")
    @login_required
    def bluetooth_scan():
        try:
            return jsonify(bluetooth.scan(12))
        except Exception as exc:
            return jsonify({"error": str(exc)[:240]}), 502

    @app.post("/bluetooth/pair")
    @login_required
    def bluetooth_pair():
        address = request.form.get("bluetooth_address", "").strip()
        try:
            device = bluetooth.pair(address)
            flash(tr("flash.bluetooth_paired", name=device.get("name", address)), "success")
        except Exception as exc:
            flash(f"Bluetooth pairing error: {str(exc)[:260]}", "error")
        return redirect(url_for("settings"))

    @app.post("/bluetooth/connect")
    @login_required
    def bluetooth_connect():
        address = request.form.get("bluetooth_address", "").strip()
        try:
            bluetooth.connect_pan(address)
            worker.force_refresh(); worker.display.wake()
            flash(tr("flash.bluetooth_connected"), "success")
        except Exception as exc:
            flash(f"Bluetooth PAN error: {str(exc)[:280]}", "error")
        return redirect(url_for("settings"))

    @app.post("/bluetooth/diagnostics")
    @login_required
    def bluetooth_diagnostics():
        address = request.form.get("bluetooth_address", "").strip()
        try:
            report = bluetooth.diagnostics(address)
            db.set_state("bluetooth:last_diagnostics", report)
            flash(tr("flash.bluetooth_diagnostics"), "success")
        except Exception as exc:
            flash(f"Bluetooth diagnostics error: {str(exc)[:500]}", "error")
        return redirect(url_for("settings"))

    @app.post("/bluetooth/disconnect")
    @login_required
    def bluetooth_disconnect():
        try:
            bluetooth.disconnect(request.form.get("bluetooth_address", "").strip())
            worker.force_refresh()
            flash(tr("flash.bluetooth_disconnected"), "success")
        except Exception as exc:
            flash(f"Bluetooth disconnect error: {str(exc)[:240]}", "error")
        return redirect(url_for("settings"))

    @app.post("/bluetooth/remove")
    @login_required
    def bluetooth_remove():
        try:
            bluetooth.remove(request.form.get("bluetooth_address", "").strip())
            flash(tr("flash.bluetooth_removed"), "success")
        except Exception as exc:
            flash(f"Bluetooth remove error: {str(exc)[:240]}", "error")
        return redirect(url_for("settings"))

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        if request.method == "POST":
            def update(current):
                lang = normalize_language(request.form.get("language", "en"))
                current["main"].update({
                    "name": request.form.get("name", "CryptoGotchi").strip() or "CryptoGotchi",
                    "language": lang,
                    "fiat": request.form.get("fiat", "eur").strip().lower() or "eur",
                    "refresh_seconds": max(30, _int("refresh_seconds", 60)),
                    "history_hours": max(24, _int("history_hours", 72)),
                    "timezone": request.form.get("timezone", "Europe/Brussels").strip() or "Europe/Brussels",
                    "max_active_assets": max(1, min(HARD_MAX_ACTIVE_ASSETS, _int("max_active_assets", 50))),
                    "config_revision": 12,
                })
                current["provider"].update({
                    "base_url": request.form.get("base_url", current["provider"]["base_url"]).strip(),
                    "chart_hours": max(1, min(48, _int("chart_hours", 24))),
                    "max_stream_jump_percent": max(2.0, min(50.0, _float("max_stream_jump_percent", 8.0))),
                })
                if request.form.get("api_key", "").strip():
                    current["provider"]["api_key"] = request.form["api_key"].strip()
                current.setdefault("connectivity", {}).update({
                    "data_saver_mode": request.form.get("data_saver_mode", "auto"),
                    "auto_on_bluetooth": _bool("auto_on_bluetooth"),
                    "auto_on_metered": _bool("auto_on_metered"),
                    "economy_refresh_seconds": max(60, _int("economy_refresh_seconds", 300)),
                    "history_backfill_in_economy": _bool("history_backfill_in_economy"),
                    "history_backfill_per_cycle": max(1, min(4, _int("history_backfill_per_cycle", 2))),
                    "public_posts_in_economy": _bool("public_posts_in_economy"),
                    "external_ai_in_economy": _bool("external_ai_in_economy"),
                })
                if current["connectivity"]["data_saver_mode"] not in {"off", "auto", "on"}:
                    current["connectivity"]["data_saver_mode"] = "auto"
                current.setdefault("personality", {}).update({
                    "profile": request.form.get("personality_profile", "sage"),
                    "show_thoughts": _bool("show_thoughts"),
                    "humor": max(0, min(100, _int("humor", 25))),
                    "energy": max(0, min(100, _int("personality_energy", 55))),
                    "prudence": max(0, min(100, _int("prudence", 80))),
                    "technical_level": max(0, min(100, _int("technical_level", 55))),
                    "talk_frequency": max(0, min(100, _int("talk_frequency", 55))),
                    "optimism": max(0, min(100, _int("optimism", 50))),
                    "verbosity": max(0, min(100, _int("verbosity", 45))),
                    "custom_identity": request.form.get("custom_identity", "").strip()[:500],
                    "animations": _bool("animations"),
                    "accessory": request.form.get("accessory", "auto"),
                })
                if current["personality"]["profile"] not in {"sage", "guardian", "explorer"}:
                    current["personality"]["profile"] = "sage"
                if current["personality"]["accessory"] not in {"auto", "none", "glasses", "cap", "crown", "shield", "antenna"}:
                    current["personality"]["accessory"] = "auto"
                current.setdefault("ai", {}).update({
                    "mode": request.form.get("ai_mode", "local"),
                    "provider": request.form.get("ai_provider", "ollama"),
                    "endpoint": request.form.get("ai_endpoint", "").strip(),
                    "model": request.form.get("ai_model", "").strip(),
                    "timeout_seconds": max(3, min(90, _int("ai_timeout_seconds", 20))),
                    "max_characters": max(80, min(800, _int("ai_max_characters", 240))),
                    "only_for_alerts": _bool("ai_only_for_alerts"),
                    "fallback_local": _bool("ai_fallback_local"),
                    "custom_system_prompt": request.form.get("ai_custom_system_prompt", "").strip()[:1200],
                })
                if request.form.get("ai_api_key", "").strip():
                    current["ai"]["api_key"] = request.form["ai_api_key"].strip()
                if current["ai"]["mode"] not in {"local", "external"}:
                    current["ai"]["mode"] = "local"
                if current["ai"]["provider"] not in {"ollama", "openai", "openai_compatible"}:
                    current["ai"]["provider"] = "ollama"
                current.setdefault("companion", {}).update({
                    "daily_journal": _bool("daily_journal"),
                    "journal_hour": max(0, min(23, _int("journal_hour", 22))),
                    "achievement_popups": _bool("achievement_popups"),
                    "interaction_cooldown_seconds": max(0, min(60, _int("interaction_cooldown_seconds", 2))),
                    "manual_message_hold_seconds": max(15, min(900, _int("manual_message_hold_seconds", 120))),
                    "max_analysis_assets": max(1, min(5, _int("max_analysis_assets", 5))),
                })
                # Ranking settings are managed by the dedicated /ranking/toggle route.
                # The normal Settings form must never erase the private server URL or token.
                current["display"].update({
                    "type": request.form.get("display_type", "waveshare_lcd_1in44"),
                    "waveshare_model": request.form.get("waveshare_model", "epd2in13_V4").strip(),
                    "rotation": _int("rotation", 0) % 360,
                    "brightness": max(0, min(100, _int("brightness", 90))),
                    "dim_brightness": max(0, min(100, _int("dim_brightness", 18))),
                    "backlight_timeout_seconds": max(0, _int("backlight_timeout_seconds", 0)),
                    "screen_sleep_seconds": max(0, _int("screen_sleep_seconds", 0)),
                    "page_cycle_seconds": max(4, _int("page_cycle_seconds", 12)),
                    "alert_hold_seconds": max(5, _int("alert_hold_seconds", 20)),
                    "auto_cycle": _bool("auto_cycle"),
                    "spi_speed_hz": max(500000, min(32000000, _int("spi_speed_hz", 9000000))),
                    "animation_fps": max(1, min(5, _int("animation_fps", 2))),
                    "show_accessories": _bool("show_accessories"),
                })
                current["market_rules"].update({
                    "enabled": _bool("market_enabled"),
                    "breadth_window_minutes": max(1, _int("breadth_window_minutes", 15)),
                    "breadth_drop_percent": abs(_float("breadth_drop_percent", 3)),
                    "breadth_count": max(1, _int("breadth_count", 3)),
                    "breadth_rise_percent": abs(_float("breadth_rise_percent", 3)),
                    "breadth_rise_count": max(1, _int("breadth_rise_count", 3)),
                    "cooldown_minutes": max(1, _int("market_cooldown_minutes", 45)),
                })
            config_manager.update(update)
            worker.display.wake(); worker.force_refresh()
            flash(translate("flash.settings_saved", normalize_language(request.form.get("language", "en"))), "success")
            return redirect(url_for("settings"))
        return render_template(
            "settings.html",
            cfg=config_manager.load(),
            connection=active_connection_info(),
            bluetooth_available=bluetooth.available(),
            bluetooth_powered=bluetooth.powered(),
            wifi_powered=bluetooth.wifi_powered(),
            supported_languages=sorted(SUPPORTED_LANGUAGES),
            ranking_status=worker.ranking.status(worker.status()),
            bluetooth_diagnostics=str(db.get_state("bluetooth:last_diagnostics", "") or ""),
        )

    @app.post("/ai/test")
    @login_required
    def ai_test():
        current = config_manager.load()
        result = worker.narrative_ai.test(current, normalize_language(current["main"].get("language")))
        if result.ok:
            flash(tr("flash.ai_test_ok", text=result.text), "success")
        else:
            flash(tr("flash.ai_test_fail", error=result.error), "error")
        return redirect(url_for("settings"))

    @app.route("/notifications", methods=["GET", "POST"])
    @login_required
    def notifications():
        if request.method == "POST":
            def update(current):
                current["security"]["allow_public_posts"] = _bool("allow_public_posts")
                current["security"]["max_public_posts_per_hour"] = max(1, _int("max_public_posts_per_hour", 3))
                current.setdefault("social_digest", {}).update({
                    "enabled": _bool("social_digest_enabled"),
                    "interval_hours": max(1, min(24, _int("social_digest_interval_hours", 4))),
                    "only_when_changed": _bool("social_digest_only_when_changed"),
                    "minimum_move_percent": max(0.0, _float("social_digest_minimum_move_percent", 0.5)),
                })
                notif = current["notifications"]
                notif["paused"] = _bool("notifications_paused")
                notif.setdefault("dashboard", {}).update({
                    "enabled": _bool("dashboard_enabled"),
                    "sound_volume": max(0, min(100, _int("dashboard_sound_volume", 65))),
                    "minimum_severity": request.form.get("dashboard_minimum_severity", "info") if request.form.get("dashboard_minimum_severity", "info") in {"info", "warning", "high", "critical"} else "info",
                    "browser_notifications": _bool("dashboard_browser_notifications"),
                })
                for channel in ("telegram", "discord", "mastodon", "bluesky", "webhook"):
                    notif[channel]["enabled"] = _bool(f"{channel}_enabled")
                fields = {
                    "telegram": ("bot_token", "chat_id"), "discord": ("webhook_url",),
                    "mastodon": ("instance_url", "access_token", "visibility"),
                    "bluesky": ("service_url", "handle", "app_password"),
                    "webhook": ("url", "bearer_token"),
                }
                for channel, keys in fields.items():
                    for key in keys:
                        value = request.form.get(f"{channel}_{key}", "").strip()
                        if value:
                            notif[channel][key] = value
            config_manager.update(update)
            flash(tr("flash.notifications_saved"), "success")
            return redirect(url_for("notifications"))
        return render_template("notifications.html", cfg=config_manager.load())

    @app.post("/notifications/test/<channel>")
    @login_required
    def test_notification(channel: str):
        if channel not in {"telegram", "discord", "mastodon", "bluesky", "webhook"}:
            abort(404)
        message = "🧪 CryptoGotchi test alert: connection successful." if language() == "en" else "🧪 Alerte de test CryptoGotchi : connexion réussie."
        alert = {
            "alert_key": "test", "coin_id": "bitcoin", "symbol": "BTC", "rule": "test",
            "severity": "info", "message": message, "ts": int(time.time()), "metrics": {}, "social_post": True,
        }
        results = worker.notifiers.dispatch(alert, test_only=channel)
        if results and results[0].get("ok"):
            flash((f"{channel} test sent." if language() == "en" else f"Test {channel} envoyé."), "success")
        else:
            error = results[0].get("error") if results else "Channel disabled or incomplete"
            flash((f"{channel} test failed: {error}" if language() == "en" else f"Échec du test {channel} : {error}"), "error")
        return redirect(url_for("notifications"))

    @app.post("/ranking/toggle")
    @login_required
    def ranking_toggle():
        enabled = request.form.get("state") == "on"
        public_name = request.form.get("ranking_public_name", "").strip()[:40]
        share_country = _bool("ranking_share_country")
        country_code = request.form.get("ranking_country_code", "").strip().upper()[:2]

        def update(current):
            ranking = current.setdefault("ranking", {})
            ranking["enabled"] = enabled
            ranking["public_name"] = public_name
            ranking["share_country"] = share_country
            ranking["country_code"] = country_code if share_country else ""
            ranking.setdefault("sync_interval_hours", 6)
            # endpoint_url and api_token are deliberately preserved. They are
            # configured by the project owner/server deployment, never exposed
            # in the public dashboard.

        config_manager.update(update)
        worker.display.wake()

        current = config_manager.load()
        endpoint = str(current.get("ranking", {}).get("endpoint_url", "") or "").strip()
        if not enabled:
            flash(
                "Participation au classement désactivée."
                if language() == "fr"
                else "Community ranking participation disabled.",
                "success",
            )
            return redirect(url_for("settings"))

        if not endpoint:
            flash(
                "Classement activé localement. La synchronisation démarrera automatiquement dès que le serveur communautaire sera configuré."
                if language() == "fr"
                else "Ranking enabled locally. Synchronization will start automatically when the community server is configured.",
                "success",
            )
            return redirect(url_for("settings"))

        result = worker.ranking.sync(worker.status(), force=True)
        if result.get("ok"):
            flash(tr("flash.ranking_ok"), "success")
        else:
            flash(tr("flash.ranking_fail", error=result.get("error", "unknown error")), "error")
        return redirect(url_for("settings"))

    @app.post("/ranking/test")
    @login_required
    def ranking_test():
        result = worker.ranking.sync(worker.status(), force=True)
        if result.get("ok"):
            flash(tr("flash.ranking_ok"), "success")
        else:
            flash(tr("flash.ranking_fail", error=result.get("error", "unknown error")), "error")
        return redirect(url_for("settings"))

    @app.post("/api/refresh")
    @login_required
    def force_refresh():
        worker.force_refresh()
        return jsonify({"ok": True, "message": "Refresh requested" if language() == "en" else "Actualisation demandée"})

    @app.post("/notifications/toggle")
    @login_required
    def toggle_notifications():
        paused = worker.toggle_notifications()
        if request.accept_mimetypes.best == "application/json" or request.headers.get("X-Requested-With") == "fetch":
            return jsonify({"ok": True, "paused": paused})
        flash(("External alerts paused." if paused else "External alerts resumed.") if language() == "en" else ("Alertes externes mises en pause." if paused else "Alertes externes réactivées."), "success")
        return redirect(request.referrer or url_for("dashboard"))

    @app.post("/display/wake")
    @login_required
    def display_wake():
        worker.display.wake()
        flash(tr("flash.display_wake"), "success")
        return redirect(url_for("settings"))

    @app.post("/display/test")
    @login_required
    def display_test():
        try:
            ok = worker.display.show_test_pattern(seconds=1.5)
        except Exception as exc:
            flash(f"Display test error: {str(exc)[:180]}", "error")
        else:
            flash(tr("flash.display_test_ok") if ok else tr("flash.display_test_off"), "success" if ok else "error")
        return redirect(url_for("settings"))

    @app.post("/display/page/<page>")
    @login_required
    def display_page(page: str):
        worker.display.set_page(page)
        return jsonify({"ok": True, "page": page})

    @app.get("/api/status")
    @login_required
    def api_status():
        current = config_manager.load()
        return jsonify({
            "status": worker.status(),
            "alerts": db.latest_alerts(25),
            "browser_alerts": current.get("notifications", {}).get("dashboard", {}),
        })

    @app.get("/api/coins/search")
    @login_required
    def api_coin_search():
        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify([])
        provider = CoinGeckoProvider(config_manager.load())
        try:
            return jsonify(provider.search(query))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 502

    @app.get("/health")
    def health():
        status = worker.status()
        return jsonify({"ok": True, "market_online": status.get("online"), "version": VERSION, "display": status.get("display")})

    if start_worker:
        bluetooth.apply_configured_state(bool(cfg.get("connectivity", {}).get("bluetooth_enabled", True)))
        worker.start()
    return app


def main() -> None:
    from waitress import serve

    logging.basicConfig(
        level=os.environ.get("CRYPTOGOTCHI_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = create_app(start_worker=True)
    cfg = app.extensions["cryptogotchi_config"].load()
    worker = app.extensions["cryptogotchi_worker"]

    def shutdown_handler(signum, frame):
        logging.getLogger(__name__).info("Shutdown requested (signal %s)", signum)
        worker.stop()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    try:
        serve(app, host=cfg["main"].get("web_host", "0.0.0.0"), port=int(cfg["main"].get("web_port", 8080)), threads=3)
    finally:
        worker.stop()


if __name__ == "__main__":
    main()
