"""Unit tests for BWYR weather layout rendering."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from PIL import Image

from custom_components.eink_esl.image.palette import BLACK, RED, WHITE, YELLOW
from custom_components.eink_esl.weather.models import (
    DayForecast,
    WeatherSnapshot,
)
from custom_components.eink_esl.weather.render import render_weather_png


def _sample_snapshot() -> WeatherSnapshot:
    return WeatherSnapshot(
        entity_id="weather.forecast_home",
        condition="clear-night",
        temperature=8.1,
        humidity=78,
        dew_point=4.3,
        pressure=1018.7,
        wind_speed=9.7,
        wind_bearing=247.2,
        cloud_coverage=3.9,
        uv_index=0.0,
        temperature_unit="°C",
        wind_speed_unit="km/h",
        pressure_unit="hPa",
        precipitation_unit="mm",
        attribution="met.no",
        days=(
            DayForecast(
                when=datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc),
                condition="partlycloudy",
                temperature=15.0,
                templow=5.0,
                humidity=60,
                precipitation=0.0,
                wind_speed=16.2,
            ),
            DayForecast(
                when=datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc),
                condition="rainy",
                temperature=10.9,
                templow=5.1,
                humidity=80,
                precipitation=6.5,
                wind_speed=26.6,
            ),
            DayForecast(
                when=datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc),
                condition="cloudy",
                temperature=12.0,
                templow=6.0,
                humidity=70,
                precipitation=0.0,
                wind_speed=10.0,
            ),
            DayForecast(
                when=datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc),
                condition="sunny",
                temperature=14.0,
                templow=7.0,
                humidity=55,
                precipitation=0.0,
                wind_speed=8.0,
            ),
            DayForecast(
                when=datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc),
                condition="partlycloudy",
                temperature=13.0,
                templow=6.0,
                humidity=60,
                precipitation=0.2,
                wind_speed=12.0,
            ),
        ),
        observed_at=datetime(2026, 10, 22, 19, 4, tzinfo=timezone.utc),
    )


def test_render_default_panel_uses_only_bwyr_pigments() -> None:
    png = render_weather_png(_sample_snapshot(), 384, 184, timezone="UTC")
    image = Image.open(BytesIO(png)).convert("RGB")
    assert image.size == (384, 184)
    allowed = {BLACK, WHITE, YELLOW, RED}
    pixels = image.load()
    colors = {
        pixels[x, y]
        for y in range(image.height)
        for x in range(image.width)
    }
    assert colors <= allowed
    assert BLACK in colors
    assert WHITE in colors


def test_render_small_panel_still_fits() -> None:
    png = render_weather_png(_sample_snapshot(), 250, 122, timezone="UTC")
    image = Image.open(BytesIO(png))
    assert image.size == (250, 122)
