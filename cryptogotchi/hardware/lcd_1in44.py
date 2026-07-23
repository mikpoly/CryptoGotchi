from __future__ import annotations

"""Pilote léger du Waveshare 1.44inch LCD HAT (ST7735S, 128x128).

Le brochage et la séquence d'initialisation suivent la documentation et le
pilote de démonstration Waveshare publiés sous licence MIT. Le pilote n'importe
les bibliothèques Raspberry Pi qu'au moment où l'écran est réellement activé,
afin de conserver le mode de développement Windows/Linux sans matériel.
"""

import logging
import time
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LCDPins:
    reset: int = 27
    data_command: int = 25
    backlight: int = 24
    key1: int = 21
    key2: int = 20
    key3: int = 16
    up: int = 6
    down: int = 19
    left: int = 5
    right: int = 26
    press: int = 13


def button_pins(pins: LCDPins) -> dict[str, int]:
    return {
        "key1": pins.key1,
        "key2": pins.key2,
        "key3": pins.key3,
        "up": pins.up,
        "down": pins.down,
        "left": pins.left,
        "right": pins.right,
        "press": pins.press,
    }


BUTTON_PINS = button_pins(LCDPins())


class GPIOProtocol(Protocol):
    def write(self, pin: int, value: int) -> None: ...
    def read(self, pin: int) -> int: ...
    def pwm(self, pin: int, duty_cycle: float) -> bool: ...
    def close(self) -> None: ...


class LGPIOBackend:
    """Backend GPIO moderne pour Raspberry Pi OS Bookworm/Trixie."""

    def __init__(self, pins: LCDPins):
        import lgpio  # type: ignore

        self._lgpio = lgpio
        self._handle = lgpio.gpiochip_open(0)
        try:
            for pin, initial in (
                (pins.reset, 1),
                (pins.data_command, 0),
                (pins.backlight, 0),
            ):
                lgpio.gpio_claim_output(self._handle, pin, initial)
            pull_up = getattr(lgpio, "SET_PULL_UP", getattr(lgpio, "SET_BIAS_PULL_UP", 32))
            for pin in button_pins(pins).values():
                lgpio.gpio_claim_input(self._handle, pin, pull_up)
        except Exception:
            lgpio.gpiochip_close(self._handle)
            raise

    def write(self, pin: int, value: int) -> None:
        self._lgpio.gpio_write(self._handle, pin, int(bool(value)))

    def read(self, pin: int) -> int:
        return int(self._lgpio.gpio_read(self._handle, pin))

    def pwm(self, pin: int, duty_cycle: float) -> bool:
        tx_pwm = getattr(self._lgpio, "tx_pwm", None)
        if not tx_pwm:
            return False
        try:
            tx_pwm(self._handle, pin, 500, max(0.0, min(100.0, duty_cycle)))
            return True
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._lgpio.gpiochip_close(self._handle)
        except Exception:
            pass


class RPiGPIOBackend:
    """Fallback pour les anciennes images Raspberry Pi OS."""

    def __init__(self, pins: LCDPins):
        import RPi.GPIO as GPIO  # type: ignore

        self._gpio = GPIO
        self._pwms: dict[int, object] = {}
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        try:
            GPIO.setup(pins.reset, GPIO.OUT, initial=GPIO.HIGH)
            GPIO.setup(pins.data_command, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(pins.backlight, GPIO.OUT, initial=GPIO.LOW)
            for pin in button_pins(pins).values():
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        except Exception:
            GPIO.cleanup()
            raise

    def write(self, pin: int, value: int) -> None:
        self._gpio.output(pin, self._gpio.HIGH if value else self._gpio.LOW)

    def read(self, pin: int) -> int:
        return int(self._gpio.input(pin))

    def pwm(self, pin: int, duty_cycle: float) -> bool:
        try:
            pwm = self._pwms.get(pin)
            if pwm is None:
                pwm = self._gpio.PWM(pin, 500)
                pwm.start(0)
                self._pwms[pin] = pwm
            pwm.ChangeDutyCycle(max(0.0, min(100.0, duty_cycle)))
            return True
        except Exception:
            return False

    def close(self) -> None:
        for pwm in self._pwms.values():
            try:
                pwm.stop()
            except Exception:
                pass
        try:
            self._gpio.cleanup()
        except Exception:
            pass


def create_gpio_backend(pins: LCDPins) -> GPIOProtocol:
    errors: list[str] = []
    try:
        return LGPIOBackend(pins)
    except Exception as exc:
        errors.append(f"lgpio: {exc}")
    try:
        return RPiGPIOBackend(pins)
    except Exception as exc:
        errors.append(f"RPi.GPIO: {exc}")
    raise RuntimeError("Aucun backend GPIO disponible (" + "; ".join(errors) + ")")


class WaveshareLCD144:
    width = 128
    height = 128
    x_offset = 1
    y_offset = 2

    def __init__(
        self,
        spi_speed_hz: int = 9_000_000,
        pins: LCDPins | None = None,
        spi=None,
        gpio: GPIOProtocol | None = None,
        initialize: bool = True,
    ):
        self.pins = pins or LCDPins()
        self.button_pins = button_pins(self.pins)
        self.gpio = gpio or create_gpio_backend(self.pins)
        try:
            self.spi = spi or self._create_spi(spi_speed_hz)
        except Exception:
            self.gpio.close()
            raise
        self.spi_speed_hz = int(spi_speed_hz)
        self._closed = False
        self._brightness = 0
        if initialize:
            try:
                self.initialize()
            except Exception:
                self.close()
                raise

    @staticmethod
    def _create_spi(speed: int):
        import spidev  # type: ignore

        spi = spidev.SpiDev()
        spi.open(0, 0)
        spi.max_speed_hz = max(500_000, min(32_000_000, int(speed)))
        spi.mode = 0
        try:
            spi.no_cs = False
        except Exception:
            pass
        return spi

    def _write(self, payload: bytes | bytearray | list[int]) -> None:
        if not payload:
            return
        if hasattr(self.spi, "writebytes2"):
            self.spi.writebytes2(list(payload))
        else:
            self.spi.writebytes(list(payload))

    def _command(self, command: int, data: bytes | bytearray | list[int] = b"") -> None:
        self.gpio.write(self.pins.data_command, 0)
        self._write([command & 0xFF])
        if data:
            self.gpio.write(self.pins.data_command, 1)
            self._write(data)

    def _reset(self) -> None:
        self.gpio.write(self.pins.reset, 1)
        time.sleep(0.10)
        self.gpio.write(self.pins.reset, 0)
        time.sleep(0.10)
        self.gpio.write(self.pins.reset, 1)
        time.sleep(0.10)

    def initialize(self) -> None:
        self.set_backlight(100)
        self._reset()
        sequence = (
            (0xB1, [0x01, 0x2C, 0x2D]),
            (0xB2, [0x01, 0x2C, 0x2D]),
            (0xB3, [0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D]),
            (0xB4, [0x07]),
            (0xC0, [0xA2, 0x02, 0x84]),
            (0xC1, [0xC5]),
            (0xC2, [0x0A, 0x00]),
            (0xC3, [0x8A, 0x2A]),
            (0xC4, [0x8A, 0xEE]),
            (0xC5, [0x0E]),
            (0xE0, [0x0F, 0x1A, 0x0F, 0x18, 0x2F, 0x28, 0x20, 0x22, 0x1F, 0x1B, 0x23, 0x37, 0x00, 0x07, 0x02, 0x10]),
            (0xE1, [0x0F, 0x1B, 0x0F, 0x17, 0x33, 0x2C, 0x29, 0x2E, 0x30, 0x30, 0x39, 0x3F, 0x00, 0x07, 0x03, 0x10]),
            (0xF0, [0x01]),
            (0xF6, [0x00]),
            (0x3A, [0x05]),  # RGB565
            (0x36, [0x68]),  # U2D_R2L + RGB, réglage Waveshare par défaut
        )
        for command, data in sequence:
            self._command(command, data)
        time.sleep(0.20)
        self._command(0x11)  # sleep out
        time.sleep(0.12)
        self._command(0x29)  # display on
        self.clear((5, 8, 12))

    def _set_window(self, x0: int, y0: int, x1: int, y1: int) -> None:
        xs = x0 + self.x_offset
        xe = x1 - 1 + self.x_offset
        ys = y0 + self.y_offset
        ye = y1 - 1 + self.y_offset
        self._command(0x2A, [0x00, xs & 0xFF, 0x00, xe & 0xFF])
        self._command(0x2B, [0x00, ys & 0xFF, 0x00, ye & 0xFF])
        self._command(0x2C)

    @staticmethod
    def image_to_rgb565(image: Image.Image) -> bytearray:
        image = image.convert("RGB")
        raw = image.tobytes()
        out = bytearray((len(raw) // 3) * 2)
        target = 0
        for source in range(0, len(raw), 3):
            r, g, b = raw[source], raw[source + 1], raw[source + 2]
            value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[target] = (value >> 8) & 0xFF
            out[target + 1] = value & 0xFF
            target += 2
        return out

    def display(self, image: Image.Image) -> None:
        if image.size != (self.width, self.height):
            raise ValueError(f"L'image doit mesurer {self.width}x{self.height} pixels")
        payload = self.image_to_rgb565(image)
        self._set_window(0, 0, self.width, self.height)
        self.gpio.write(self.pins.data_command, 1)
        for start in range(0, len(payload), 4096):
            self._write(payload[start:start + 4096])

    def clear(self, color: tuple[int, int, int] = (0, 0, 0)) -> None:
        self.display(Image.new("RGB", (self.width, self.height), color))

    def set_backlight(self, brightness: int | float) -> None:
        value = max(0.0, min(100.0, float(brightness)))
        self._brightness = int(round(value))
        if not self.gpio.pwm(self.pins.backlight, value):
            self.gpio.write(self.pins.backlight, 1 if value > 0 else 0)

    def pressed_buttons(self) -> set[str]:
        # Les boutons sont actifs à l'état bas et disposent de résistances pull-up.
        return {name for name, pin in self.button_pins.items() if self.gpio.read(pin) == 0}

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._command(0x28)  # display off
        except Exception:
            pass
        try:
            self.set_backlight(0)
        except Exception:
            pass
        try:
            self.spi.close()
        except Exception:
            pass
        self.gpio.close()
