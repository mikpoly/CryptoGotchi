from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo
from typing import Any


@dataclass
class SessionWindow:
    name: str
    timezone: str
    open_time: dtime
    close_time: dtime


NYSE = SessionWindow("NYSE", "America/New_York", dtime(9, 30), dtime(16, 0))


def _safe_zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or "UTC"))
    except Exception:
        return ZoneInfo("UTC")


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    value = date(year, month, day)
    if value.weekday() == 5:
        return value - timedelta(days=1)
    if value.weekday() == 6:
        return value + timedelta(days=1)
    return value


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    current += timedelta(days=7 * (n - 1))
    return current


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _easter_sunday(year: int) -> date:
    # Anonymous Gregorian algorithm.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def nyse_holidays(year: int) -> set[date]:
    easter = _easter_sunday(year)
    return {
        _observed_fixed_holiday(year, 1, 1),
        _nth_weekday(year, 1, 0, 3),  # MLK
        _nth_weekday(year, 2, 0, 3),  # Presidents
        easter - timedelta(days=2),   # Good Friday
        _last_weekday(year, 5, 0),    # Memorial Day
        _observed_fixed_holiday(year, 6, 19),
        _observed_fixed_holiday(year, 7, 4),
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4), # Thanksgiving
        _observed_fixed_holiday(year, 12, 25),
    }


def _format_local(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")


def _crypto_session(user_tz: ZoneInfo, now_local: datetime, language: str) -> dict[str, Any]:
    return {
        "market_name": "Crypto 24/7",
        "market_timezone": "UTC",
        "status": "open",
        "summary": "Marché crypto ouvert 24 h/24 et 7 j/7" if language == "fr" else "Crypto market open 24/7",
        "local_now": _format_local(now_local),
        "session_open_local": "",
        "session_close_local": "",
        "next_event_label": "",
        "next_event_local": "",
        "enhanced_window": False,
    }


def _metals_session(user_tz: ZoneInfo, now_utc: datetime, now_local: datetime, language: str) -> dict[str, Any]:
    weekday = now_utc.weekday()  # Monday=0
    minute_of_day = now_utc.hour * 60 + now_utc.minute
    open_now = weekday < 4 or (weekday == 4 and minute_of_day < 22 * 60) or (weekday == 6 and minute_of_day >= 22 * 60)
    summary = (
        "Métaux spot quasi 24/5 ; le marché de référence ferme le week-end." if language == "fr" else
        "Spot metals are roughly 24/5; the reference market closes on weekends."
    )
    return {
        "market_name": "Spot metals",
        "market_timezone": "UTC",
        "status": "open" if open_now else "closed",
        "summary": summary,
        "local_now": _format_local(now_local),
        "session_open_local": "",
        "session_close_local": "",
        "next_event_label": "",
        "next_event_local": "",
        "enhanced_window": False,
    }


def _nyse_session(user_tz: ZoneInfo, now_local: datetime, language: str) -> dict[str, Any]:
    market_tz = _safe_zone(NYSE.timezone)
    market_now = now_local.astimezone(market_tz)
    holidays = nyse_holidays(market_now.year)
    current_day = market_now.date()
    is_open_day = market_now.weekday() < 5 and current_day not in holidays
    open_dt_market = datetime.combine(current_day, NYSE.open_time, tzinfo=market_tz)
    close_dt_market = datetime.combine(current_day, NYSE.close_time, tzinfo=market_tz)
    opening_soon_minutes = 30
    closing_soon_minutes = 30
    if not is_open_day:
        next_day = current_day + timedelta(days=1)
        while next_day.weekday() >= 5 or next_day in nyse_holidays(next_day.year):
            next_day += timedelta(days=1)
        next_open = datetime.combine(next_day, NYSE.open_time, tzinfo=market_tz)
        summary = (
            f"NYSE fermé. Prochaine ouverture locale : {next_open.astimezone(user_tz).strftime('%H:%M')}" if language == "fr" else
            f"NYSE closed. Next local open: {next_open.astimezone(user_tz).strftime('%H:%M')}"
        )
        return {
            "market_name": NYSE.name,
            "market_timezone": NYSE.timezone,
            "status": "closed",
            "summary": summary,
            "local_now": _format_local(now_local),
            "session_open_local": _format_local(next_open.astimezone(user_tz)),
            "session_close_local": "",
            "next_event_label": "open" if language == "en" else "ouverture",
            "next_event_local": _format_local(next_open.astimezone(user_tz)),
            "enhanced_window": False,
        }
    if market_now < open_dt_market:
        minutes = int((open_dt_market - market_now).total_seconds() // 60)
        summary = (
            f"NYSE avant ouverture, ouverture locale dans {minutes} min" if language == "fr" else
            f"NYSE pre-open, local open in {minutes} min"
        )
        return {
            "market_name": NYSE.name,
            "market_timezone": NYSE.timezone,
            "status": "pre_open",
            "summary": summary,
            "local_now": _format_local(now_local),
            "session_open_local": _format_local(open_dt_market.astimezone(user_tz)),
            "session_close_local": _format_local(close_dt_market.astimezone(user_tz)),
            "next_event_label": "open" if language == "en" else "ouverture",
            "next_event_local": _format_local(open_dt_market.astimezone(user_tz)),
            "enhanced_window": minutes <= opening_soon_minutes,
        }
    if market_now <= close_dt_market:
        minutes_open = int((market_now - open_dt_market).total_seconds() // 60)
        minutes_to_close = int((close_dt_market - market_now).total_seconds() // 60)
        state = "open"
        if minutes_open <= opening_soon_minutes:
            summary = (
                f"NYSE ouvert depuis {minutes_open} min ; fenêtre d'ouverture active." if language == "fr" else
                f"NYSE open for {minutes_open} min; opening window active."
            )
        elif minutes_to_close <= closing_soon_minutes:
            summary = (
                f"NYSE proche de la clôture, fermeture locale dans {minutes_to_close} min." if language == "fr" else
                f"NYSE near close, local close in {minutes_to_close} min."
            )
        else:
            summary = (
                "NYSE en séance normale." if language == "fr" else "NYSE regular session."
            )
        return {
            "market_name": NYSE.name,
            "market_timezone": NYSE.timezone,
            "status": state,
            "summary": summary,
            "local_now": _format_local(now_local),
            "session_open_local": _format_local(open_dt_market.astimezone(user_tz)),
            "session_close_local": _format_local(close_dt_market.astimezone(user_tz)),
            "next_event_label": "close" if language == "en" else "clôture",
            "next_event_local": _format_local(close_dt_market.astimezone(user_tz)),
            "enhanced_window": minutes_open <= opening_soon_minutes or minutes_to_close <= closing_soon_minutes,
        }
    next_day = current_day + timedelta(days=1)
    while next_day.weekday() >= 5 or next_day in nyse_holidays(next_day.year):
        next_day += timedelta(days=1)
    next_open = datetime.combine(next_day, NYSE.open_time, tzinfo=market_tz)
    summary = (
        f"NYSE fermé après séance. Prochaine ouverture locale : {next_open.astimezone(user_tz).strftime('%H:%M')}" if language == "fr" else
        f"NYSE closed after session. Next local open: {next_open.astimezone(user_tz).strftime('%H:%M')}"
    )
    return {
        "market_name": NYSE.name,
        "market_timezone": NYSE.timezone,
        "status": "closed",
        "summary": summary,
        "local_now": _format_local(now_local),
        "session_open_local": _format_local(next_open.astimezone(user_tz)),
        "session_close_local": "",
        "next_event_label": "open" if language == "en" else "ouverture",
        "next_event_local": _format_local(next_open.astimezone(user_tz)),
        "enhanced_window": False,
    }


def describe_market_session(market: dict[str, Any], timezone_name: str | None, language: str = "en") -> dict[str, Any]:
    language = "fr" if language == "fr" else "en"
    user_tz = _safe_zone(timezone_name)
    now_local = datetime.now(user_tz)
    now_utc = now_local.astimezone(ZoneInfo("UTC"))
    trading_mode = str(market.get("trading_mode") or "24x7").lower()
    asset_kind = str(market.get("asset_kind") or "crypto").lower()
    symbol = str(market.get("symbol") or "")
    if trading_mode == "24x7" and asset_kind not in {"tokenized_asset"}:
        return _crypto_session(user_tz, now_local, language)
    if asset_kind == "commodity" or str(market.get("source") or "") == "gold_api":
        return _metals_session(user_tz, now_utc, now_local, language)
    if asset_kind == "tokenized_asset" or symbol in {"SPXC"} or trading_mode == "market_session":
        return _nyse_session(user_tz, now_local, language)
    return _crypto_session(user_tz, now_local, language)
