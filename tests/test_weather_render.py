"""Unit tests for BWYR weather layout rendering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO

from PIL import Image

from custom_components.eink_esl.image.palette import BLACK, RED, WHITE, YELLOW
from custom_components.eink_esl.weather.models import (
    DayForecast,
    HourlyForecast,
    WeatherSnapshot,
)
from custom_components.eink_esl.weather.render import render_weather_png


def _sample_snapshot() -> WeatherSnapshot:
    start = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    hours = tuple(
        HourlyForecast(
            when=start + timedelta(hours=i),
            condition="rainy" if i < 4 else "cloudy",
            temperature=10.0 - i * 0.3,
            humidity=70 + i,
            precipitation=1.2 if i < 3 else 0.0,
            wind_speed=20 + i,
            wind_bearing=170 + i * 5,
            cloud_coverage=90.0,
        )
        for i in range(18)
    )
    return WeatherSnapshot(
        entity_id="weather.forecast_home",
        condition="rainy",
        temperature=9.9,
        humidity=65,
        dew_point=3.4,
        pressure=1004.0,
        wind_speed=29.5,
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
                precipitation=0.0,
                wind_speed=10.0,
                wind_bearing=180.0,
                cloud_coverage=80.0,
            ),
            DayForecast(
                when=datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc),
                condition="sunny",
                temperature=14.0,
                templow=7.0,
                humidity=55,
                precipitation=0.0,
                wind_speed=8.0,
                wind_bearing=90.0,
                cloud_coverage=10.0,
            ),
        ),
        hours=hours,
        observed_at=datetime(2026, 10, 25, 11, 0, tzinfo=timezone.utc),
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
