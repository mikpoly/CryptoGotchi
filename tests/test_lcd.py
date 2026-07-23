from __future__ import annotations

from PIL import Image
import sys
import types

from cryptogotchi.hardware.lcd_1in44 import LCDPins, LGPIOBackend, WaveshareLCD144
from cryptogotchi.lcd_renderer import LCD144Renderer


class FakeSPI:
    def __init__(self):
        self.writes: list[list[int]] = []
        self.closed = False

    def writebytes2(self, payload):
        self.writes.append(list(payload))

    def close(self):
        self.closed = True


class FakeGPIO:
    def __init__(self):
        self.values: dict[int, int] = {}
        self.writes: list[tuple[int, int]] = []
        self.pwm_values: list[tuple[int, float]] = []
        self.closed = False

    def write(self, pin: int, value: int) -> None:
        self.values[pin] = value
        self.writes.append((pin, value))

    def read(self, pin: int) -> int:
        return self.values.get(pin, 1)

    def pwm(self, pin: int, duty_cycle: float) -> bool:
        self.pwm_values.append((pin, duty_cycle))
        return True

    def close(self) -> None:
        self.closed = True


def sample_status():
    return {
        "online": True,
        "state": "bullish",
        "message": "Le marché accélère avec énergie.",
        "notifications_paused": False,
        "breadth": {"up": 2, "down": 0, "flat": 0, "average": 1.8},
        "system": {
            "ip": "192.168.1.44",
            "wifi_ssid": "Maison",
            "wifi_signal": 78,
            "cpu_temp_c": 44.2,
            "memory_percent": 37,
            "uptime": "2h 14m",
        },
        "coins": [
            {
                "id": "bitcoin",
                "symbol": "BTC",
                "name": "Bitcoin",
                "price": 103245.2,
                "change_24h": 4.21,
                "metrics": {"5m": 0.4, "15m": 1.3, "1h": 2.1},
                "sparkline": [100, 99, 101, 102, 105],
            },
            {
                "id": "ethereum",
                "symbol": "ETH",
                "name": "Ethereum",
                "price": 3421.5,
                "change_24h": -0.31,
                "metrics": {"5m": -0.1, "15m": 0.2, "1h": 0.8},
                "sparkline": [100, 101, 100, 102],
            },
        ],
        "last_alert": {
            "symbol": "BTC",
            "rule": "rise_15m",
            "severity": "high",
            "message": "BTC progresse rapidement de +3,20% en 15m.",
            "ts": 1_700_000_000,
        },
    }


def test_renderer_outputs_all_128px_pages():
    renderer = LCD144Renderer()
    config = {"main": {"name": "CryptoGotchi", "fiat": "eur"}, "display": {"rotation": 0}}
    for page in range(len(renderer.pages)):
        image = renderer.render(sample_status(), page=page, config=config)
        assert image.mode == "RGB"
        assert image.size == (128, 128)
        # Le rendu ne doit pas être un écran uniforme.
        assert len(image.getcolors(maxcolors=128 * 128) or []) > 4


def test_rgb565_conversion_known_colors():
    image = Image.new("RGB", (3, 1))
    image.putdata([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
    assert WaveshareLCD144.image_to_rgb565(image) == bytearray([0xF8, 0x00, 0x07, 0xE0, 0x00, 0x1F])


def test_lcd_display_and_buttons_with_fake_hardware():
    spi = FakeSPI()
    gpio = FakeGPIO()
    lcd = WaveshareLCD144(spi=spi, gpio=gpio, initialize=False)
    lcd.display(Image.new("RGB", (128, 128), (255, 0, 0)))

    # 128 x 128 x 2 octets de pixels, envoyés par blocs.
    assert sum(len(chunk) for chunk in spi.writes if len(chunk) > 100) == 32768
    # Les commandes CASET/RASET/RAMWR sont présentes.
    command_bytes = [chunk[0] for chunk in spi.writes if len(chunk) == 1]
    assert 0x2A in command_bytes
    assert 0x2B in command_bytes
    assert 0x2C in command_bytes

    gpio.values[lcd.pins.key1] = 0
    gpio.values[lcd.pins.right] = 0
    assert lcd.pressed_buttons() == {"key1", "right"}

    lcd.set_backlight(42)
    assert gpio.pwm_values[-1] == (lcd.pins.backlight, 42.0)
    lcd.close()
    assert spi.closed is True
    assert gpio.closed is True


def test_lgpio_backend_uses_current_python_argument_order(monkeypatch):
    calls = []
    fake = types.SimpleNamespace(
        SET_BIAS_PULL_UP=123,
        gpiochip_open=lambda chip: 77,
        gpio_claim_output=lambda handle, gpio, level=0, lFlags=0: calls.append(("out", handle, gpio, level, lFlags)),
        gpio_claim_input=lambda handle, gpio, lFlags=0: calls.append(("in", handle, gpio, lFlags)),
        gpio_write=lambda handle, gpio, value: 0,
        gpio_read=lambda handle, gpio: 1,
        gpiochip_close=lambda handle: 0,
    )
    monkeypatch.setitem(sys.modules, "lgpio", fake)
    backend = LGPIOBackend(LCDPins())
    assert calls[0] == ("out", 77, 27, 1, 0)
    assert calls[3] == ("in", 77, 21, 123)
    backend.close()
