"""Load a weather snapshot from Home Assistant (state + get_forecasts)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import WeatherError
from .models import WeatherSnapshot, snapshot_from_state_and_forecast

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

DEFAULT_WEATHER_DAYS = 5


async def async_fetch_weather_snapshot(
    hass: HomeAssistant,
    entity_id: str,
    *,
    max_days: int = DEFAULT_WEATHER_DAYS,
) -> WeatherSnapshot:
    """Read current weather attrs and daily forecast for ``entity_id``."""
    from homeassistant.util import dt as dt_util

    entity_id = entity_id.strip()
    if not entity_id.startswith("weather."):
        raise WeatherError(f"Not a weather entity: {entity_id}")

    state = hass.states.get(entity_id)
    if state is None:
        raise WeatherError(f"Weather entity not found: {entity_id}")
    if state.state in ("unavailable", "unknown"):
        raise WeatherError(f"Weather entity is {state.state}: {entity_id}")

    try:
        response = await hass.services.async_call(
            "weather",
            "get_forecasts",
            service_data={"type": "daily"},
            target={"entity_id": entity_id},
            blocking=True,
            return_response=True,
        )
    except Exception as err:  # noqa: BLE001 - map any HA/provider failure
        raise WeatherError(f"Could not load daily forecast: {err}") from err

    forecast_days: list[dict] = []
    if isinstance(response, dict):
        payload = response.get(entity_id) or {}
        raw = payload.get("forecast") if isinstance(payload, dict) else None
        if isinstance(raw, list):
            forecast_days = [row for row in raw if isinstance(row, dict)]

    # Skip "today" when it duplicates current (met.no day[0] is often now).
    days_for_strip = forecast_days
    if len(forecast_days) > 1:
        days_for_strip = forecast_days[1:]

    observed = state.last_updated
    if observed is not None and getattr(observed, "tzinfo", None) is None:
        observed = dt_util.as_utc(observed)

    return snapshot_from_state_and_forecast(
        entity_id=entity_id,
        state=state.state,
        attributes=dict(state.attributes),
        forecast_days=days_for_strip,
        observed_at=observed,
        max_days=max_days,
    )


def list_weather_entity_ids(hass: HomeAssistant) -> list[str]:
    """Return weather entity ids sorted by friendly name then entity id."""
    labeled: list[tuple[str, str]] = []
    for entity_id in hass.states.async_entity_ids("weather"):
        state = hass.states.get(entity_id)
        if state is None:
            continue
        name = str(state.attributes.get("friendly_name") or entity_id)
        labeled.append((name.lower(), entity_id))
    labeled.sort()
    return [entity_id for _, entity_id in labeled]
