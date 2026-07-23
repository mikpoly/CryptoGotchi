from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

WIDTH = 128
HEIGHT = 128

FONT_PATHS = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
]
BOLD_FONT_PATHS = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
]

STATE_COLORS = {
    "offline": (120, 128, 140),
    "sleeping": (106, 130, 164),
    "calm": (76, 157, 220),
    "curious": (240, 184, 60),
    "bullish": (49, 203, 128),
    "bearish": (242, 113, 113),
    "panic": (255, 72, 89),
    "euphoric": (180, 108, 255),
}

STATE_LABELS = {
    "en": {
        "offline": "OFFLINE", "sleeping": "SLEEPY", "calm": "CALM", "curious": "CURIOUS",
        "bullish": "BULLISH", "bearish": "BEARISH", "panic": "ALERT", "euphoric": "EUPHORIC",
    },
    "fr": {
        "offline": "HORS LIGNE", "sleeping": "ENDORMI", "calm": "CALME", "curious": "CURIEUX",
        "bullish": "HAUSSIER", "bearish": "BAISSIER", "panic": "ALERTE", "euphoric": "EUPHORIQUE",
    },
}


class Fonts:
    def __init__(self):
        self.tiny = self._load(8)
        self.small = self._load(9)
        self.normal = self._load(11)
        self.medium = self._load(13, bold=True)
        self.large = self._load(18, bold=True)
        self.huge = self._load(26, bold=True)

    @staticmethod
    def _load(size: int, bold: bool = False):
        paths = BOLD_FONT_PATHS if bold else FONT_PATHS
        for path in paths:
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), size=size)
                except OSError:
                    pass
        return ImageFont.load_default()


class LCD144Renderer:
    pages = ("home", "coin", "market", "companion", "journal", "achievement", "alert", "system")

    def __init__(self):
        self.fonts = Fonts()

    @staticmethod
    def _lang(config: dict[str, Any]) -> str:
        return "fr" if config.get("main", {}).get("language") == "fr" else "en"

    @staticmethod
    def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
        box = draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0]

    def _fit_text(self, draw: ImageDraw.ImageDraw, text: str, max_width: int, font, max_chars: int = 60) -> str:
        text = str(text).strip()
        if self._text_width(draw, text, font) <= max_width:
            return text
        while text and self._text_width(draw, text + "…", font) > max_width:
            text = text[:-1]
        return (text[:max_chars] + "…") if text else "…"

    def _wrap(self, draw: ImageDraw.ImageDraw, text: str, max_width: int, font, max_lines: int) -> list[str]:
        words = self._lcd_text(text).split()
        lines: list[str] = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if self._text_width(draw, trial, font) <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
                if len(lines) >= max_lines:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)
        if len(lines) == max_lines and " ".join(lines) != " ".join(words):
            lines[-1] = self._fit_text(draw, lines[-1], max_width, font)
        return lines[:max_lines]

    @staticmethod
    def _fmt_price(value: Any, fiat: str = "EUR") -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "--"
        if abs(number) >= 1000:
            text = f"{number:,.0f}"
        elif abs(number) >= 1:
            text = f"{number:,.2f}"
        elif abs(number) >= 0.01:
            text = f"{number:.4f}"
        else:
            text = f"{number:.7f}".rstrip("0")
        return f"{text} {fiat.upper()}"

    @staticmethod
    def _fmt_pct(value: Any) -> str:
        if value is None:
            return "--"
        try:
            return f"{float(value):+.2f}%"
        except (TypeError, ValueError):
            return "--"

    @staticmethod
    def _lcd_text(value: Any) -> str:
        text = str(value)
        for token in ("🟢", "🔴", "🚨", "🚀", "⚠️", "⚠", "👀", "🧪", "📓", "👑", "⭐", "💙", "🔥", "🛡", "📡", "💯", "🔭", "🔔", "📅", "🧭"):
            text = text.replace(token, "")
        return " ".join(text.split())

    @staticmethod
    def _metric_color(value: Any) -> tuple[int, int, int]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return (142, 154, 168)
        if number > 0.05:
            return (70, 225, 145)
        if number < -0.05:
            return (255, 105, 120)
        return (190, 198, 208)

    def _header(self, draw: ImageDraw.ImageDraw, status: dict[str, Any], title: str, page_index: int) -> None:
        state = str(status.get("state", "offline"))
        accent = STATE_COLORS.get(state, STATE_COLORS["calm"])
        draw.rectangle((0, 0, 127, 14), fill=(15, 20, 28))
        draw.rectangle((0, 0, 3, 14), fill=accent)
        draw.text((7, 2), self._fit_text(draw, title, 62, self.fonts.small), font=self.fonts.small, fill=(238, 243, 248))
        companion = status.get("companion", {}) or {}
        level = int(companion.get("level", 1) or 1)
        engine = str(companion.get("engine", "micro-brain-v2"))
        draw.text((71, 2), f"L{level}", font=self.fonts.tiny, fill=(178, 132, 255))
        if engine.startswith("external"):
            draw.text((84, 2), "AI", font=self.fonts.tiny, fill=(83, 202, 255))
        elif bool((status.get("network", {}) or {}).get("economy", {}).get("active")):
            draw.text((84, 2), "E", font=self.fonts.tiny, fill=(245, 184, 68))
        paused = bool(status.get("notifications_paused"))
        draw.text((96, 2), "M" if paused else "N", font=self.fonts.tiny, fill=(255, 181, 71) if paused else (81, 218, 145))
        draw.text((116, 2), str(page_index + 1), font=self.fonts.tiny, fill=(143, 157, 173))

    @staticmethod
    def _blink(frame: int) -> bool:
        return frame % 17 in {0, 1}

    def _accessory(self, draw: ImageDraw.ImageDraw, accessory: str, cx: int, cy: int, radius: int, accent: tuple[int, int, int]) -> None:
        if accessory == "glasses":
            draw.rectangle((cx - 22, cy - 15, cx - 5, cy - 1), outline=(111, 210, 255), width=2)
            draw.rectangle((cx + 5, cy - 15, cx + 22, cy - 1), outline=(111, 210, 255), width=2)
            draw.line((cx - 5, cy - 8, cx + 5, cy - 8), fill=(111, 210, 255), width=2)
        elif accessory == "cap":
            draw.arc((cx - 24, cy - radius - 7, cx + 18, cy - radius + 15), 190, 350, fill=(80, 170, 255), width=4)
            draw.line((cx + 8, cy - radius + 3, cx + 27, cy - radius + 5), fill=(80, 170, 255), width=3)
        elif accessory == "crown":
            points = [(cx - 21, cy - radius + 3), (cx - 14, cy - radius - 12), (cx - 3, cy - radius), (cx + 7, cy - radius - 13), (cx + 20, cy - radius + 3)]
            draw.line(points, fill=(255, 208, 72), width=3)
            draw.line((cx - 21, cy - radius + 3, cx + 20, cy - radius + 3), fill=(255, 208, 72), width=3)
        elif accessory == "shield":
            draw.polygon([(cx + radius - 3, cy + 2), (cx + radius + 13, cy + 8), (cx + radius + 9, cy + 27), (cx + radius - 3, cy + 34), (cx + radius - 15, cy + 27), (cx + radius - 19, cy + 8)], outline=(120, 180, 255), fill=(20, 50, 85))
        elif accessory == "antenna":
            draw.line((cx, cy - radius, cx, cy - radius - 12), fill=accent, width=2)
            draw.ellipse((cx - 3, cy - radius - 17, cx + 3, cy - radius - 11), fill=(255, 196, 70))

    def _particles(self, draw: ImageDraw.ImageDraw, state: str, frame: int) -> None:
        accent = STATE_COLORS.get(state, STATE_COLORS["calm"])
        if state in {"bullish", "euphoric"}:
            for idx in range(4):
                x = 9 + idx * 30
                y = 82 - ((frame * 2 + idx * 13) % 60)
                draw.line((x, y + 5, x, y), fill=accent, width=1)
                draw.line((x, y, x - 2, y + 3), fill=accent)
                draw.line((x, y, x + 2, y + 3), fill=accent)
        elif state in {"bearish", "panic"}:
            for idx in range(4):
                x = 12 + idx * 29
                y = 25 + ((frame * 2 + idx * 11) % 65)
                draw.line((x, y, x, y + 5), fill=accent, width=1)
                draw.line((x, y + 5, x - 2, y + 2), fill=accent)
                draw.line((x, y + 5, x + 2, y + 2), fill=accent)
        elif state == "sleeping":
            for idx in range(3):
                x = 86 + idx * 8
                y = 25 - ((frame + idx * 5) % 13)
                draw.text((x, y), "z", font=self.fonts.tiny, fill=accent)

    def _draw_face(self, draw: ImageDraw.ImageDraw, state: str, companion: dict[str, Any], frame: int, center=(64, 49), radius=25) -> None:
        """Render a compact robot instead of a Unicode/circular face."""
        accent = STATE_COLORS.get(state, STATE_COLORS["calm"])
        cx, cy = center
        bob = int(math.sin(frame / 3.0) * 1) if state not in {"panic", "offline"} else 0
        cy += bob
        # antenna + signal
        draw.line((cx, cy - 34, cx, cy - 27), fill=(66, 91, 111), width=2)
        draw.ellipse((cx - 3, cy - 39, cx + 3, cy - 33), fill=accent)
        if frame % 8 < 4:
            draw.arc((cx - 11, cy - 43, cx + 11, cy - 27), 205, 335, fill=accent, width=1)
        # ears and head shell
        draw.rounded_rectangle((cx - 35, cy - 23, cx - 28, cy + 8), radius=3, fill=(11, 20, 29), outline=(52, 75, 94))
        draw.rounded_rectangle((cx + 28, cy - 23, cx + 35, cy + 8), radius=3, fill=(11, 20, 29), outline=(52, 75, 94))
        draw.rounded_rectangle((cx - 30, cy - 28, cx + 30, cy + 18), radius=12, fill=(14, 24, 34), outline=accent, width=2)
        draw.rounded_rectangle((cx - 25, cy - 23, cx + 25, cy + 13), radius=9, fill=(5, 12, 18), outline=(38, 58, 74))
        eye_y = cy - 10
        blink = self._blink(frame)
        if state == "sleeping" or blink:
            draw.line((cx - 17, eye_y, cx - 8, eye_y), fill=accent, width=2)
            draw.line((cx + 8, eye_y, cx + 17, eye_y), fill=accent, width=2)
        elif state in {"panic", "offline"}:
            draw.rectangle((cx - 17, eye_y - 4, cx - 9, eye_y + 4), outline=accent, width=2)
            draw.rectangle((cx + 9, eye_y - 4, cx + 17, eye_y + 4), outline=accent, width=2)
        else:
            glance = -1 if frame % 12 < 4 else 1 if frame % 12 > 8 else 0
            draw.rounded_rectangle((cx - 17 + glance, eye_y - 4, cx - 9 + glance, eye_y + 4), radius=3, fill=accent)
            draw.rounded_rectangle((cx + 9 + glance, eye_y - 4, cx + 17 + glance, eye_y + 4), radius=3, fill=accent)
        if state in {"bullish", "euphoric", "curious", "calm"}:
            draw.arc((cx - 12, cy - 1, cx + 12, cy + 11), 8, 172, fill=accent, width=2)
        elif state in {"bearish", "panic", "offline"}:
            draw.arc((cx - 12, cy + 4, cx + 12, cy + 16), 190, 350, fill=accent, width=2)
        else:
            draw.line((cx - 9, cy + 7, cx + 9, cy + 7), fill=accent, width=2)
        # body, core and feet
        draw.rounded_rectangle((cx - 23, cy + 19, cx + 23, cy + 36), radius=6, fill=(12, 22, 31), outline=(48, 70, 87))
        draw.ellipse((cx - 4, cy + 23, cx + 4, cy + 31), fill=accent)
        draw.line((cx - 13, cy + 36, cx - 17, cy + 40), fill=(58, 80, 97), width=3)
        draw.line((cx + 13, cy + 36, cx + 17, cy + 40), fill=(58, 80, 97), width=3)
        self._accessory(draw, str(companion.get("accessory", "none")), cx, cy, 27, accent)


    def _home(self, draw: ImageDraw.ImageDraw, status: dict[str, Any], language: str, frame: int) -> None:
        state = str(status.get("state", "offline"))
        companion = status.get("companion", {}) or {}
        self._particles(draw, state, frame)
        self._draw_face(draw, state, companion, frame, center=(64, 47), radius=25)
        label = STATE_LABELS[language].get(state, state.upper())
        accent = STATE_COLORS.get(state, STATE_COLORS["calm"])
        w = self._text_width(draw, label, self.fonts.small)
        draw.rounded_rectangle(((128 - w) // 2 - 5, 89, (128 + w) // 2 + 5, 102), radius=6, fill=(12, 23, 33), outline=accent)
        draw.text(((128 - w) // 2, 91), label, font=self.fonts.small, fill=accent)
        message = str(status.get("message", "Starting…" if language == "en" else "Démarrage…"))
        lines = self._wrap(draw, message, 118, self.fonts.tiny, 2)
        y = 106
        for line in lines:
            tw = self._text_width(draw, line, self.fonts.tiny)
            draw.text(((128 - tw) // 2, y), line, font=self.fonts.tiny, fill=(205, 214, 224))
            y += 9


    def _sparkline(self, draw: ImageDraw.ImageDraw, values: list[Any], box: tuple[int, int, int, int], color: tuple[int, int, int], language: str) -> None:
        nums: list[float] = []
        for value in values:
            try:
                nums.append(float(value))
            except (TypeError, ValueError):
                continue
        x0, y0, x1, y1 = box
        draw.rounded_rectangle(box, radius=5, fill=(7, 14, 21), outline=(35, 57, 73))
        for ratio in (0.33, 0.66):
            gy = y0 + int((y1 - y0) * ratio)
            for gx in range(x0 + 3, x1 - 2, 6):
                draw.point((gx, gy), fill=(28, 45, 58))
        if len(nums) < 2:
            text = "fresh history…" if language == "en" else "historique frais…"
            draw.text((x0 + 5, y0 + 9), text, font=self.fonts.tiny, fill=(93, 107, 123))
            return
        low, high = min(nums), max(nums)
        raw_span = high - low
        center = (high + low) / 2.0
        padding = max(raw_span * 0.14, abs(center) * 0.0005, 1e-12)
        low -= padding; high += padding
        span = high - low or 1.0
        points = []
        for idx, value in enumerate(nums):
            x = x0 + 3 + int(idx * max(1, x1 - x0 - 6) / max(1, len(nums) - 1))
            y = y1 - 3 - int((value - low) * max(1, y1 - y0 - 6) / span)
            points.append((x, y))
        draw.line(points, fill=color, width=2)
        px, py = points[-1]
        draw.ellipse((px - 2, py - 2, px + 2, py + 2), fill=color, outline=(7, 14, 21))


    def _coin(self, draw: ImageDraw.ImageDraw, status: dict[str, Any], coin_index: int, fiat: str, language: str) -> None:
        coins = status.get("coins", []) or []
        if not coins:
            draw.text((12, 43), "No asset" if language == "en" else "Aucun actif", font=self.fonts.medium, fill=(210, 218, 228))
            draw.text((12, 63), "Add one on the Web" if language == "en" else "Ajoute-en via le Web", font=self.fonts.small, fill=(126, 141, 158))
            return
        coin = coins[coin_index % len(coins)]
        symbol = str(coin.get("symbol", "?"))[:8]
        kind = str(coin.get("asset_kind", "crypto"))
        status_key = "STALE" if coin.get("is_stale") else ("CLOSED" if coin.get("market_status") == "closed" else "LIVE")
        status_color = (255, 104, 119) if status_key == "STALE" else ((247, 190, 68) if status_key == "CLOSED" else (72, 220, 145))
        draw.text((5, 18), symbol, font=self.fonts.large, fill=(239, 244, 250))
        draw.rounded_rectangle((84, 19, 123, 31), radius=5, fill=(12, 24, 34), outline=status_color)
        sw = self._text_width(draw, status_key, self.fonts.tiny)
        draw.text((103 - sw // 2, 21), status_key, font=self.fonts.tiny, fill=status_color)
        change = coin.get("metrics", {}).get("15m")
        if change is None:
            change = coin.get("metrics", {}).get("1h")
        pct = self._fmt_pct(change)
        draw.text((5, 39), self._fit_text(draw, self._fmt_price(coin.get("price"), str(coin.get("fiat") or fiat)), 82, self.fonts.medium), font=self.fonts.medium, fill=(126, 207, 255))
        pw = self._text_width(draw, pct, self.fonts.small)
        draw.text((123 - pw, 42), pct, font=self.fonts.small, fill=self._metric_color(change))
        spark = coin.get("sparkline") or []
        trend_value = spark[-1] - spark[0] if len(spark) > 1 else 0
        self._sparkline(draw, spark, (5, 57, 122, 91), self._metric_color(trend_value), language)
        kind_short = {"commodity": "METAL", "tokenized_asset": "TOKEN", "crypto_token": "TOKEN", "meme": "MEME"}.get(kind, "CRYPTO")
        draw.text((8, 60), kind_short, font=self.fonts.tiny, fill=(92, 112, 130))
        metrics = coin.get("metrics", {}) or {}
        labels = [("5m", metrics.get("5m")), ("15m", metrics.get("15m")), ("1h", metrics.get("1h")), ("24h", coin.get("change_24h"))]
        for x, (label, value) in zip((5, 36, 68, 98), labels):
            draw.text((x, 97), label, font=self.fonts.tiny, fill=(113, 128, 145))
            draw.text((x, 108), self._fmt_pct(value), font=self.fonts.tiny, fill=self._metric_color(value))
        provider = "GOLD" if coin.get("source") == "gold_api" else "CG"
        draw.text((5, 119), provider, font=self.fonts.tiny, fill=(90, 179, 225))
        if kind != "crypto":
            note = "excluded from crypto mood" if language == "en" else "hors humeur crypto"
            draw.text((123 - self._text_width(draw, note, self.fonts.tiny), 119), note, font=self.fonts.tiny, fill=(127, 139, 151))


    def _market(self, draw: ImageDraw.ImageDraw, status: dict[str, Any], language: str) -> None:
        coins = status.get("coins", []) or []
        if not coins:
            draw.text((9, 48), "Waiting for market…" if language == "en" else "Marché en attente…", font=self.fonts.normal, fill=(175, 187, 201))
            return
        y = 18
        for coin in coins[:6]:
            symbol = str(coin.get("symbol", "?"))[:6]
            change = coin.get("metrics", {}).get("15m")
            if change is None:
                change = coin.get("change_24h")
            badge = "M" if coin.get("asset_kind") == "commodity" else ("T" if coin.get("asset_kind") in {"tokenized_asset", "crypto_token"} else "C")
            draw.text((5, y), badge, font=self.fonts.tiny, fill=(245, 190, 76) if badge != "C" else (84, 200, 255))
            draw.text((15, y), symbol, font=self.fonts.small, fill=(225, 232, 240))
            pct = "CLOSED" if coin.get("market_status") == "closed" else self._fmt_pct(change)
            w = self._text_width(draw, pct, self.fonts.small if pct != "CLOSED" else self.fonts.tiny)
            draw.text((123 - w, y), pct, font=self.fonts.small if pct != "CLOSED" else self.fonts.tiny, fill=(247, 190, 68) if pct == "CLOSED" else self._metric_color(change))
            draw.line((5, y + 13, 123, y + 13), fill=(29, 39, 51))
            y += 17
        breadth = status.get("breadth", {}) or {}
        draw.text((5, 112), f"CRYPTO ↑{breadth.get('up', 0)}", font=self.fonts.tiny, fill=(71, 220, 141))
        draw.text((55, 112), f"↓{breadth.get('down', 0)}", font=self.fonts.tiny, fill=(255, 107, 121))
        score = breadth.get("average")
        text = self._fmt_pct(score)
        draw.text((123 - self._text_width(draw, text, self.fonts.tiny), 112), text, font=self.fonts.tiny, fill=self._metric_color(score))


    def _bar(self, draw: ImageDraw.ImageDraw, label: str, value: Any, y: int, color: tuple[int, int, int]) -> None:
        try:
            number = max(0, min(100, int(float(value))))
        except (TypeError, ValueError):
            number = 0
        draw.text((5, y), label, font=self.fonts.tiny, fill=(135, 150, 168))
        draw.rectangle((43, y + 1, 112, y + 7), fill=(25, 34, 45), outline=(48, 61, 76))
        draw.rectangle((44, y + 2, 44 + int(66 * number / 100), y + 6), fill=color)
        draw.text((115, y), str(number), font=self.fonts.tiny, fill=(210, 218, 228))

    def _companion(self, draw: ImageDraw.ImageDraw, status: dict[str, Any], language: str, frame: int) -> None:
        companion = status.get("companion", {}) or {}
        self._bar(draw, "ENG" if language == "en" else "NRJ", companion.get("energy"), 20, (73, 211, 145))
        self._bar(draw, "STR", companion.get("stress"), 34, (255, 99, 116))
        self._bar(draw, "CONF", companion.get("confidence"), 48, (91, 174, 255))
        self._bar(draw, "CUR", companion.get("curiosity"), 62, (245, 187, 69))
        self._bar(draw, "BOND" if language == "en" else "LIEN", companion.get("bond"), 76, (182, 112, 255))
        level = int(companion.get("level", 1) or 1)
        xp = int(companion.get("xp", 0) or 0)
        next_xp = int(companion.get("next_level_xp", level * 120) or level * 120)
        draw.text((5, 93), f"L{level}  XP {xp}/{next_xp}", font=self.fonts.small, fill=(220, 227, 236))
        age = int(companion.get("age_days", 0) or 0)
        streak = int(companion.get("active_streak", 1) or 1)
        draw.text((5, 107), (f"Age {age}d  Streak {streak}d" if language == "en" else f"Âge {age}j  Série {streak}j"), font=self.fonts.tiny, fill=(126, 141, 158))
        draw.text((5, 118), ("Press: ask · K3: pet" if language == "en" else "Press: avis · K3: caresse"), font=self.fonts.tiny, fill=(82, 101, 121))

    def _journal(self, draw: ImageDraw.ImageDraw, status: dict[str, Any], language: str) -> None:
        journals = status.get("journals", []) or []
        if not journals:
            text = "No daily journal yet. Keep watching." if language == "en" else "Pas encore de journal. Continue la veille."
            lines = self._wrap(draw, text, 116, self.fonts.small, 7)
            y = 28
        else:
            entry = journals[0]
            draw.text((5, 19), str(entry.get("day", "")), font=self.fonts.small, fill=(91, 199, 255))
            lines = self._wrap(draw, entry.get("text", ""), 116, self.fonts.small, 8)
            y = 34
        for line in lines:
            draw.text((6, y), line, font=self.fonts.small, fill=(222, 229, 238))
            y += 11

    def _achievement(self, draw: ImageDraw.ImageDraw, status: dict[str, Any], language: str) -> None:
        achievement = (status.get("companion", {}) or {}).get("new_achievement")
        if not achievement:
            count = int((status.get("companion", {}) or {}).get("achievement_count", 0) or 0)
            draw.text((18, 35), "ACHIEVEMENTS" if language == "en" else "SUCCÈS", font=self.fonts.medium, fill=(255, 205, 75))
            draw.text((42, 62), str(count), font=self.fonts.huge, fill=(255, 225, 120))
            draw.text((23, 98), "Keep exploring" if language == "en" else "Continue d'explorer", font=self.fonts.small, fill=(142, 157, 174))
            return
        draw.rounded_rectangle((8, 23, 119, 104), radius=12, fill=(31, 25, 16), outline=(255, 203, 71), width=2)
        draw.text((27, 31), "UNLOCKED" if language == "en" else "DÉBLOQUÉ", font=self.fonts.medium, fill=(255, 219, 105))
        title = self._fit_text(draw, achievement.get("title", "Achievement"), 104, self.fonts.medium)
        draw.text(((128 - self._text_width(draw, title, self.fonts.medium)) // 2, 57), title, font=self.fonts.medium, fill=(245, 247, 250))
        lines = self._wrap(draw, achievement.get("description", ""), 96, self.fonts.tiny, 3)
        y = 79
        for line in lines:
            draw.text(((128 - self._text_width(draw, line, self.fonts.tiny)) // 2, y), line, font=self.fonts.tiny, fill=(181, 188, 198))
            y += 9

    def _alert(self, draw: ImageDraw.ImageDraw, status: dict[str, Any], language: str) -> None:
        alert = status.get("last_alert") or {}
        if not alert:
            draw.text((8, 38), "No alert" if language == "en" else "Aucune alerte", font=self.fonts.medium, fill=(87, 218, 151))
            draw.text((8, 60), "Thresholds are active." if language == "en" else "Les seuils sont surveillés.", font=self.fonts.small, fill=(149, 163, 179))
            return
        severity = str(alert.get("severity", "info"))
        accent = (255, 76, 91) if severity in {"critical", "high"} else (245, 184, 68)
        draw.rounded_rectangle((5, 20, 123, 44), radius=7, fill=(42, 20, 26), outline=accent, width=2)
        symbol = str(alert.get("symbol") or "ALERT")[:10]
        draw.text((10, 25), symbol, font=self.fonts.medium, fill=accent)
        rule = str(alert.get("rule", "")).replace("_", " ")[:18]
        draw.text((119 - self._text_width(draw, rule, self.fonts.tiny), 29), rule, font=self.fonts.tiny, fill=(205, 164, 171))
        lines = self._wrap(draw, alert.get("message", ""), 116, self.fonts.small, 6)
        y = 51
        for line in lines:
            draw.text((6, y), line, font=self.fonts.small, fill=(232, 237, 243))
            y += 11
        if alert.get("ts"):
            draw.text((6, 116), time.strftime("%H:%M:%S", time.localtime(int(alert["ts"]))), font=self.fonts.tiny, fill=(117, 130, 145))

    def _system(self, draw: ImageDraw.ImageDraw, status: dict[str, Any], language: str) -> None:
        info = status.get("system", {}) or {}
        network = status.get("network", {}) or {}
        economy = network.get("economy", {}) or {}
        connection = economy.get("connection", {}) or {}
        entries = [
            ("IP", info.get("ip") or "--"),
            ("LINK" if language == "en" else "LIEN", connection.get("type") or "--"),
            ("DATA", "ECO" if economy.get("active") else "NORMAL"),
            ("CPU", f"{info.get('cpu_temp_c'):.1f}°C" if isinstance(info.get("cpu_temp_c"), (int, float)) else "--"),
            ("RAM", f"{info.get('memory_percent'):.0f}%" if isinstance(info.get("memory_percent"), (int, float)) else "--"),
            ("ALERT" if language == "en" else "ALERTE", "PAUSED" if status.get("notifications_paused") else "ACTIVE"),
        ]
        y = 19
        for label, value in entries:
            draw.text((5, y), label, font=self.fonts.tiny, fill=(112, 128, 146))
            text = self._fit_text(draw, str(value), 84, self.fonts.small)
            draw.text((123 - self._text_width(draw, text, self.fonts.small), y - 1), text, font=self.fonts.small, fill=(222, 230, 239))
            y += 17
        draw.text((5, 119), "K1 refresh  K2 mute" if language == "en" else "K1 refresh  K2 pause", font=self.fonts.tiny, fill=(85, 100, 117))

    def render(self, status: dict[str, Any], page: int = 0, coin_index: int = 0, config: dict[str, Any] | None = None, frame: int = 0) -> Image.Image:
        cfg = config or {}
        language = self._lang(cfg)
        display_cfg = cfg.get("display", {})
        main_cfg = cfg.get("main", {})
        image = Image.new("RGB", (WIDTH, HEIGHT), (7, 10, 15))
        draw = ImageDraw.Draw(image)
        page_index = page % len(self.pages)
        page_name = self.pages[page_index]
        titles = {
            "en": {"home": str(main_cfg.get("name", "CryptoGotchi")), "coin": "Asset detail", "market": "Market view", "companion": "Companion", "journal": "Daily journal", "achievement": "Achievements", "alert": "Latest alert", "system": "Raspberry Pi"},
            "fr": {"home": str(main_cfg.get("name", "CryptoGotchi")), "coin": "Détail actif", "market": "Vue marché", "companion": "Compagnon", "journal": "Journal quotidien", "achievement": "Succès", "alert": "Dernière alerte", "system": "Raspberry Pi"},
        }
        self._header(draw, status, titles[language][page_name], page_index)
        if page_name == "home":
            self._home(draw, status, language, frame)
        elif page_name == "coin":
            self._coin(draw, status, coin_index, str(main_cfg.get("fiat", "eur")), language)
        elif page_name == "market":
            self._market(draw, status, language)
        elif page_name == "companion":
            self._companion(draw, status, language, frame)
        elif page_name == "journal":
            self._journal(draw, status, language)
        elif page_name == "achievement":
            self._achievement(draw, status, language)
        elif page_name == "alert":
            self._alert(draw, status, language)
        else:
            self._system(draw, status, language)
        rotation = int(display_cfg.get("rotation", 0)) % 360
        if rotation in {90, 180, 270}:
            image = image.rotate(rotation, expand=False)
        return image

    def test_pattern(self, name: str = "CryptoGotchi") -> Image.Image:
        image = Image.new("RGB", (WIDTH, HEIGHT), (5, 8, 13))
        draw = ImageDraw.Draw(image)
        for x in range(WIDTH):
            draw.line((x, 0, x, 15), fill=(int(255 * x / 127), 70, int(255 * (127 - x) / 127)))
        draw.rounded_rectangle((8, 24, 119, 100), radius=12, fill=(17, 25, 36), outline=(65, 196, 255), width=2)
        draw.text((20, 35), "LCD 1.44 OK", font=self.fonts.medium, fill=(83, 211, 255))
        draw.text((16, 58), "ST7735S 128x128", font=self.fonts.small, fill=(224, 232, 242))
        draw.text((18, 77), self._fit_text(draw, name, 92, self.fonts.small), font=self.fonts.small, fill=(86, 224, 146))
        draw.text((28, 108), "by mikpoly", font=self.fonts.small, fill=(139, 151, 168))
        return image
