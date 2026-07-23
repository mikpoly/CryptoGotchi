from __future__ import annotations

import argparse
import time

from .hardware.lcd_1in44 import WaveshareLCD144
from .lcd_renderer import LCD144Renderer


def main() -> None:
    parser = argparse.ArgumentParser(description="Test du Waveshare 1.44inch LCD HAT")
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--brightness", type=int, default=90)
    parser.add_argument("--spi-speed", type=int, default=9_000_000)
    args = parser.parse_args()
    lcd = WaveshareLCD144(spi_speed_hz=args.spi_speed)
    try:
        lcd.set_backlight(args.brightness)
        lcd.display(LCD144Renderer().test_pattern())
        time.sleep(max(1.0, args.seconds))
    finally:
        lcd.close()


if __name__ == "__main__":
    main()
