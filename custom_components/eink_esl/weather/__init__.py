"""Weather snapshot + BWYR layout for ESL panels (no BLE)."""

from __future__ import annotations

from .errors import WeatherError
from .models import DayForecast, WeatherSnapshot
from .render import render_weather_png

__all__ = [
    "DayForecast",
    "WeatherError",
    "WeatherSnapshot",
    "async_fetch_weather_snapshot",
    "list_weather_entity_ids",
    "render_weather_png",
]


def __getattr__(name: str):
    """Lazy-load HA-bound helpers so unit tests need no Home Assistant."""
    if name == "async_fetch_weather_snapshot":
        from .fetch import async_fetch_weather_snapshot

        return async_fetch_weather_snapshot
    if name == "list_weather_entity_ids":
        from .fetch import list_weather_entity_ids

        return list_weather_entity_ids
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
