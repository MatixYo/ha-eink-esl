#!/usr/bin/env python3
"""Render weather card PNG locally (no HA / no release needed).

Uses the same Home Assistant import stubs as unit tests so you can iterate
on layout on a Mac without installing HA or shipping a new HACS release.

Examples:
  .venv/bin/python scripts/preview_weather.py --open
  .venv/bin/python scripts/preview_weather.py --zoom 3 --open
  .venv/bin/python scripts/preview_weather.py --lang en --panel bwry-213
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _install_homeassistant_stubs() -> None:
    """Minimal stubs so ``custom_components.eink_esl`` imports without HA."""

    def module(name: str) -> types.ModuleType:
        existing = sys.modules.get(name)
        if existing is not None:
            return existing
        created = types.ModuleType(name)
        created.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = created
        return created

    ha = module("homeassistant")
    ha.__path__ = []  # type: ignore[attr-defined]
    const = module("homeassistant.const")
    const.Platform = type("Platform", (), {"SENSOR": "sensor"})  # type: ignore[attr-defined]
    module("homeassistant.config_entries")
    module("homeassistant.core")
    module("homeassistant.exceptions")
    module("homeassistant.helpers")
    module("homeassistant.helpers.device_registry")
    module("homeassistant.helpers.storage")
    module("homeassistant.helpers.config_validation")
    module("homeassistant.components")
    module("homeassistant.components.bluetooth")


_install_homeassistant_stubs()

from custom_components.eink_esl.protocol.panels import (  # noqa: E402
    DEFAULT_PANEL_ID,
    PANELS,
    panel_by_id,
)
from custom_components.eink_esl.weather.models import (  # noqa: E402
    DayForecast,
    HourlyForecast,
    WeatherSnapshot,
)
from custom_components.eink_esl.weather.render import (  # noqa: E402
    render_weather_png,
)


def _sample_snapshot() -> WeatherSnapshot:
    """Realistic-ish met.no shaped sample spanning three calendar days."""
    start = datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc)
    hours = tuple(
        HourlyForecast(
            when=start + timedelta(hours=i),
            condition=(
                "rainy"
                if i < 10
                else "cloudy"
                if i < 36
                else "partlycloudy"
            ),
            temperature=7.5
            + 4.0 * abs((i % 24) - 12) / 12.0
            + (i // 24) * 0.8,
            humidity=78 - (i % 24),
            precipitation=(
                2.4
                if i < 5
                else 0.8
                if i < 9
                else 1.1
                if 28 <= i < 32
                else 0.0
            ),
            wind_speed=18 + (i % 5),
            wind_bearing=170 + (i % 24) * 4,
            cloud_coverage=95.0 if i < 20 else 45.0,
        )
        for i in range(72)
    )
    return WeatherSnapshot(
        entity_id="weather.forecast_home",
        location_name="Warszawa",
        condition="rainy",
        temperature=9.9,
        humidity=65,
        dew_point=3.4,
        pressure=1004.0,
        wind_speed=29.5,
        wind_gust_speed=44.0,
        wind_bearing=177.4,
        cloud_coverage=100.0,
        uv_index=1.9,
        temperature_unit="°C",
        wind_speed_unit="km/h",
        pressure_unit="hPa",
        precipitation_unit="mm",
        attribution="met.no",
        days=(
            DayForecast(
                when=datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc),
                condition="rainy",
                temperature=10.9,
                templow=8.7,
                humidity=65,
                precipitation=6.2,
                wind_speed=29.5,
                wind_bearing=177.4,
                cloud_coverage=100.0,
            ),
            DayForecast(
                when=datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc),
                condition="partlycloudy",
                temperature=15.0,
                templow=5.0,
                humidity=60,
                precipitation=0.0,
                wind_speed=16.2,
                wind_bearing=200.0,
                cloud_coverage=40.0,
            ),
            DayForecast(
                when=datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc),
                condition="cloudy",
                temperature=12.0,
                templow=6.0,
                humidity=70,
                precipitation=1.1,
                wind_speed=10.0,
                wind_bearing=180.0,
                cloud_coverage=80.0,
            ),
        ),
        hours=hours,
        observed_at=datetime(2026, 10, 25, 11, 0, tzinfo=timezone.utc),
    )


def _parse_size(text: str) -> tuple[int, int]:
    text = text.lower().strip()
    if "x" not in text:
        raise argparse.ArgumentTypeError("Use WIDTHxHEIGHT, e.g. 384x184")
    left, right = text.split("x", 1)
    return int(left), int(right)


def _resolve_size(args: argparse.Namespace) -> tuple[int, int]:
    if args.size:
        return args.size
    panel = panel_by_id(args.panel)
    return panel.width, panel.height


def main() -> int:
    panel_choices = [p.id for p in PANELS]
    parser = argparse.ArgumentParser(
        description="Preview e-ink weather PNG without Home Assistant."
    )
    parser.add_argument(
        "--panel",
        default=DEFAULT_PANEL_ID,
        choices=panel_choices,
        help=f"Panel model (default: {DEFAULT_PANEL_ID})",
    )
    parser.add_argument(
        "--size",
        type=_parse_size,
        default=None,
        help="Override size as WIDTHxHEIGHT (e.g. 384x184)",
    )
    parser.add_argument(
        "--lang",
        choices=("pl", "en"),
        default="pl",
        help="UI language (default: pl)",
    )
    parser.add_argument(
        "--tz",
        default="Europe/Warsaw",
        help="Timezone for labels (default: Europe/Warsaw)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "tmp" / "weather_preview.png",
        help="Output PNG path",
    )
    parser.add_argument(
        "--zoom",
        type=int,
        default=1,
        help="Integer nearest-neighbor zoom for viewing (default: 1)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the PNG with the system viewer (macOS open)",
    )
    args = parser.parse_args()

    width, height = _resolve_size(args)
    png = render_weather_png(
        _sample_snapshot(),
        width,
        height,
        timezone=args.tz,
        language=args.lang,
    )

    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.zoom > 1:
        from io import BytesIO

        from PIL import Image

        image = Image.open(BytesIO(png))
        zoomed = image.resize(
            (width * args.zoom, height * args.zoom),
            resample=Image.Resampling.NEAREST,
        )
        zoomed.save(out)
    else:
        out.write_bytes(png)

    print(f"Wrote {out} ({width}x{height}, lang={args.lang})")
    if args.open:
        subprocess.run(["open", str(out)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
