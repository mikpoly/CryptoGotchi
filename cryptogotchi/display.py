from __future__ import annotations

import importlib
import logging
import threading
import time
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont

from .config import ConfigManager
from .lcd_renderer import LCD144Renderer

log = logging.getLogger(__name__)


class DisplayManager:
    """Gestion centralisée des écrans, du joystick et du rétroéclairage."""

    def __init__(self, config: ConfigManager):
        self.config_manager = config
        self.driver: Any = None
        self.driver_name: str | None = None
        self.driver_error: str | None = None
        self._driver_signature: tuple[Any, ...] | None = None
        self.renderer = LCD144Renderer()
        self._lock = threading.RLock()
        self._latest_status: dict[str, Any] = {
            "online": False,
            "state": "offline",
            "message": "Starting CryptoGotchi…",
            "coins": [],
        }
        self._page = 0
        self._coin_index = 0
        self._last_alert_ts = 0
        self._alert_page_until = 0.0
        self._auto_cycle_override: bool | None = None
        self._last_page_change = time.monotonic()
        self._last_interaction = time.monotonic()
        self._last_brightness: int | None = None
        self._controls_stop = threading.Event()
        self._controls_thread: threading.Thread | None = None
        self._on_force_refresh: Callable[[], None] | None = None
        self._on_toggle_notifications: Callable[[], None] | None = None
        self._on_ask_coin: Callable[[], None] | None = None
        self._on_pet: Callable[[], None] | None = None
        self._animation_frame = 0
        self._last_animation = time.monotonic()

    def set_callbacks(
        self,
        on_force_refresh: Callable[[], None] | None = None,
        on_toggle_notifications: Callable[[], None] | None = None,
        on_ask_coin: Callable[[], None] | None = None,
        on_pet: Callable[[], None] | None = None,
    ) -> None:
        self._on_force_refresh = on_force_refresh
        self._on_toggle_notifications = on_toggle_notifications
        self._on_ask_coin = on_ask_coin
        self._on_pet = on_pet

    def info(self) -> dict[str, Any]:
        return {
            "type": self.driver_name or self.config_manager.load().get("display", {}).get("type", "virtual"),
            "page": self.renderer.pages[self._page % len(self.renderer.pages)],
            "coin_index": self._coin_index,
            "error": self.driver_error,
            "controls": bool(self._controls_thread and self._controls_thread.is_alive()),
        }

    def _ensure_driver(self) -> None:
        cfg = self.config_manager.load().get("display", {})
        requested = str(cfg.get("type", "virtual"))
        # Compatibilité avec le nom historique de la v0.1.0.
        if requested == "waveshare":
            requested = "waveshare_epaper"
        if requested not in {"waveshare_lcd_1in44", "waveshare_epaper", "virtual"}:
            requested = "virtual"
        signature: tuple[Any, ...]
        if requested == "waveshare_lcd_1in44":
            signature = (requested, int(cfg.get("spi_speed_hz", 9_000_000)))
        elif requested == "waveshare_epaper":
            signature = (requested, str(cfg.get("waveshare_model", "epd2in13_V4")))
        else:
            signature = ("virtual",)
        if signature == self._driver_signature and (requested == "virtual" or self.driver is not None):
            return
        self.close()
        self.driver_name = requested
        self._driver_signature = signature
        self.driver_error = None
        if requested == "waveshare_lcd_1in44":
            try:
                from .hardware.lcd_1in44 import WaveshareLCD144

                self.driver = WaveshareLCD144(spi_speed_hz=int(cfg.get("spi_speed_hz", 9_000_000)))
                self._set_backlight(int(cfg.get("brightness", 90)))
                self._start_controls()
                log.info("Waveshare 1.44inch LCD HAT initialisé")
            except Exception as exc:
                self.driver_error = str(exc)
                log.exception("LCD 1.44 indisponible; l'interface Web reste active")
                self.driver = None
        elif requested == "waveshare_epaper":
            try:
                model = cfg.get("waveshare_model", "epd2in13_V4")
                module = importlib.import_module(f"waveshare_epd.{model}")
                epd = module.EPD()
                epd.init()
                self.driver = (epd, Image, ImageDraw, ImageFont)
            except Exception as exc:
                self.driver_error = str(exc)
                log.warning("E-paper Waveshare indisponible: %s", exc)
                self.driver = None
        else:
            self.driver_name = "virtual"
            self.driver = None

    def _start_controls(self) -> None:
        self._controls_stop.clear()
        self._controls_thread = threading.Thread(target=self._controls_loop, name="cryptogotchi-lcd-controls", daemon=True)
        self._controls_thread.start()

    def _set_backlight(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        if self._last_brightness == value:
            return
        driver = self.driver
        if driver and self.driver_name == "waveshare_lcd_1in44":
            try:
                driver.set_backlight(value)
                self._last_brightness = value
            except Exception as exc:
                log.debug("Réglage rétroéclairage impossible: %s", exc)

    def _wake(self) -> None:
        self._last_interaction = time.monotonic()
        cfg = self.config_manager.load().get("display", {})
        self._set_backlight(int(cfg.get("brightness", 90)))

    def wake(self) -> bool:
        """Réveille le LCD depuis l'interface Web ou une action interne."""
        self._ensure_driver()
        self._wake()
        if self.driver_name == "waveshare_lcd_1in44" and self.driver:
            self._render_lcd()
            return True
        return False

    def _controls_loop(self) -> None:
        previous: set[str] = set()
        last_housekeeping = 0.0
        while not self._controls_stop.wait(0.05):
            driver = self.driver
            if not driver or self.driver_name != "waveshare_lcd_1in44":
                return
            try:
                pressed = driver.pressed_buttons()
            except Exception as exc:
                self.driver_error = str(exc)
                log.warning("Lecture des boutons impossible: %s", exc)
                return
            newly_pressed = pressed - previous
            previous = pressed
            for button in ("up", "down", "left", "right", "press", "key1", "key2", "key3"):
                if button in newly_pressed:
                    self._handle_button(button)
            now = time.monotonic()
            if now - last_housekeeping >= 0.5:
                last_housekeeping = now
                self._housekeeping(now)

    def _housekeeping(self, now: float) -> None:
        cfg = self.config_manager.load().get("display", {})
        auto_cycle = bool(cfg.get("auto_cycle", True)) if self._auto_cycle_override is None else self._auto_cycle_override
        cycle_seconds = max(4, int(cfg.get("page_cycle_seconds", 12)))
        if auto_cycle and now >= self._alert_page_until and now - self._last_page_change >= cycle_seconds:
            with self._lock:
                self._page = (self._page + 1) % len(self.renderer.pages)
                self._last_page_change = now
            self._render_lcd()
        personality = self.config_manager.load().get("personality", {})
        fps = max(1, min(4, int(cfg.get("animation_fps", 2))))
        page_name = self.renderer.pages[self._page % len(self.renderer.pages)]
        if personality.get("animations", True) and page_name in {"home", "companion"} and now - self._last_animation >= 1.0 / fps:
            self._animation_frame = (self._animation_frame + 1) % 120
            self._last_animation = now
            self._render_lcd()
        idle = now - self._last_interaction
        sleep_after = max(0, int(cfg.get("screen_sleep_seconds", 0)))
        dim_after = max(0, int(cfg.get("backlight_timeout_seconds", 0)))
        if sleep_after and idle >= sleep_after:
            self._set_backlight(0)
        elif dim_after and idle >= dim_after:
            self._set_backlight(int(cfg.get("dim_brightness", 18)))
        else:
            self._set_backlight(int(cfg.get("brightness", 90)))

    def _handle_button(self, button: str) -> None:
        self._wake()
        now = time.monotonic()
        callback: Callable[[], None] | None = None
        with self._lock:
            coins = self._latest_status.get("coins", []) or []
            if button == "up":
                self._page = (self._page - 1) % len(self.renderer.pages)
            elif button == "down":
                self._page = (self._page + 1) % len(self.renderer.pages)
            elif button == "left":
                self._coin_index = (self._coin_index - 1) % max(1, len(coins))
                self._page = 1
            elif button == "right":
                self._coin_index = (self._coin_index + 1) % max(1, len(coins))
                self._page = 1
            elif button == "press":
                self._page = self.renderer.pages.index("companion")
                callback = self._on_ask_coin
            elif button == "key1":
                callback = self._on_force_refresh
            elif button == "key2":
                callback = self._on_toggle_notifications
            elif button == "key3":
                self._page = self.renderer.pages.index("companion")
                callback = self._on_pet
            self._last_page_change = now
            self._alert_page_until = 0
        self._render_lcd()
        if callback:
            try:
                callback()
            except Exception as exc:
                log.warning("Action bouton %s impossible: %s", button, exc)

    def set_page(self, page: int | str) -> None:
        with self._lock:
            if isinstance(page, str):
                try:
                    page = self.renderer.pages.index(page)
                except ValueError:
                    page = 0
            self._page = int(page) % len(self.renderer.pages)
            self._last_page_change = time.monotonic()
            self._alert_page_until = 0
        self._wake()
        self._render_lcd()

    def update(self, status: dict[str, Any]) -> None:
        self._ensure_driver()
        with self._lock:
            self._latest_status = status
            coin_count = len(status.get("coins", []) or [])
            self._coin_index %= max(1, coin_count)
            alert = status.get("last_alert") or {}
            alert_ts = int(alert.get("ts") or 0)
            if alert_ts > self._last_alert_ts:
                self._last_alert_ts = alert_ts
                if self.driver_name == "waveshare_lcd_1in44":
                    hold = max(5, int(self.config_manager.load().get("display", {}).get("alert_hold_seconds", 20)))
                    self._page = self.renderer.pages.index("alert")
                    self._alert_page_until = time.monotonic() + hold
                    self._last_page_change = time.monotonic()
                    self._wake()
            elif (status.get("companion") or {}).get("new_achievement") and self.config_manager.load().get("companion", {}).get("achievement_popups", True):
                self._page = self.renderer.pages.index("achievement")
                self._alert_page_until = time.monotonic() + 12
                self._last_page_change = time.monotonic()
                self._wake()
        if self.driver_name == "waveshare_lcd_1in44":
            self._render_lcd()
        elif self.driver_name == "waveshare_epaper":
            self._render_epaper(status)

    def _render_lcd(self) -> None:
        with self._lock:
            driver = self.driver
            if not driver or self.driver_name != "waveshare_lcd_1in44":
                return
            status = self._latest_status
            cfg = self.config_manager.load()
            page = self._page
            coin_index = self._coin_index
            try:
                image = self.renderer.render(status, page=page, coin_index=coin_index, config=cfg, frame=self._animation_frame)
                driver.display(image)
                self.driver_error = None
            except Exception as exc:
                self.driver_error = str(exc)
                log.warning("Mise à jour LCD 1.44 impossible: %s", exc)

    def _render_epaper(self, status: dict[str, Any]) -> None:
        if not self.driver:
            return
        epd, image_module, draw_module, font_module = self.driver
        try:
            width, height = int(epd.height), int(epd.width)
            image = image_module.new("1", (width, height), 255)
            draw = draw_module.Draw(image)
            font = font_module.load_default()
            title = f"CryptoGotchi [{status.get('state', '?').upper()}]"
            draw.text((4, 4), title[:38], font=font, fill=0)
            y = 20
            for coin in status.get("coins", [])[:4]:
                change = coin.get("metrics", {}).get("15m")
                if change is None:
                    change = coin.get("change_24h")
                change_text = "--" if change is None else f"{change:+.2f}%"
                line = f"{coin.get('symbol','?')}: {coin.get('price',0):.8g} {change_text}"
                draw.text((4, y), line[:38], font=font, fill=0)
                y += 14
            message = str(status.get("message", ""))
            draw.text((4, height - 28), message[:38], font=font, fill=0)
            draw.text((4, height - 14), message[38:76], font=font, fill=0)
            rotation = int(self.config_manager.load().get("display", {}).get("rotation", 180))
            if rotation:
                image = image.rotate(rotation, expand=False)
            epd.display(epd.getbuffer(image))
            self.driver_error = None
        except Exception as exc:
            self.driver_error = str(exc)
            log.warning("Mise à jour e-paper impossible: %s", exc)

    def show_test_pattern(self, seconds: float = 0.0) -> bool:
        self._ensure_driver()
        if self.driver_name != "waveshare_lcd_1in44" or not self.driver:
            return False
        cfg = self.config_manager.load()
        self._wake()
        image = self.renderer.test_pattern(str(cfg.get("main", {}).get("name", "CryptoGotchi")))
        rotation = int(cfg.get("display", {}).get("rotation", 0)) % 360
        if rotation in {90, 180, 270}:
            image = image.rotate(rotation, expand=False)
        self.driver.display(image)
        if seconds > 0:
            time.sleep(seconds)
            self._render_lcd()
        return True

    def close(self) -> None:
        self._controls_stop.set()
        thread = self._controls_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._controls_thread = None
        driver = self.driver
        driver_name = self.driver_name
        self.driver = None
        self.driver_name = None
        self._driver_signature = None
        self._last_brightness = None
        if driver:
            try:
                if driver_name == "waveshare_epaper":
                    driver[0].sleep()
                else:
                    driver.close()
            except Exception:
                pass
