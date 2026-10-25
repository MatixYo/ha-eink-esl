"""HA-facing helper: fetch snapshot and render panel PNG."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .errors import WeatherError
from .fetch import async_fetch_weather_snapshot
from .render import render_weather_png

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..device import EinkEslDevice


async def async_generate_weather_png(
    hass: HomeAssistant,
    device: EinkEslDevice,
    entity_id: str,
) -> tuple[bytes, int, int]:
    """Return ``(png_bytes, width, height)`` for the device's panel model."""
    from ..protocol import panel_by_id

    snapshot = await async_fetch_weather_snapshot(hass, entity_id)
    panel = panel_by_id(device.panel_id)
    try:
        png = await asyncio.to_thread(
            render_weather_png,
            snapshot,
            panel.width,
            panel.height,
            timezone=hass.config.time_zone,
            language="pl",
        )
    except WeatherError:
        raise
    except Exception as err:  # noqa: BLE001
        raise WeatherError(f"Weather render failed: {err}") from err
    return png, panel.width, panel.height
