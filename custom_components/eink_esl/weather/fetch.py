"""Load a weather snapshot from Home Assistant (state + get_forecasts)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .errors import WeatherError
from .models import WeatherSnapshot, snapshot_from_state_and_forecast

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Today + two more days (third optional if provider returns it).
DEFAULT_WEATHER_DAYS = 4
DEFAULT_WEATHER_HOURS = 24


async def _async_forecast(
    hass: HomeAssistant, entity_id: str, forecast_type: str
) -> list[dict[str, Any]]:
    try:
        response = await hass.services.async_call(
            "weather",
            "get_forecasts",
            service_data={"type": forecast_type},
            target={"entity_id": entity_id},
            blocking=True,
            return_response=True,
        )
    except Exception as err:  # noqa: BLE001
        if forecast_type == "daily":
            raise WeatherError(
                f"Could not load daily forecast: {err}"
            ) from err
        return []

    if not isinstance(response, dict):
        return []
    payload = response.get(entity_id) or {}
    raw = payload.get("forecast") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


async def async_fetch_weather_snapshot(
    hass: HomeAssistant,
    entity_id: str,
    *,
    max_days: int = DEFAULT_WEATHER_DAYS,
    max_hours: int = DEFAULT_WEATHER_HOURS,
) -> WeatherSnapshot:
    """Read current weather attrs plus daily and hourly forecasts."""
    from homeassistant.util import dt as dt_util

    entity_id = entity_id.strip()
    if not entity_id.startswith("weather."):
        raise WeatherError(f"Not a weather entity: {entity_id}")

    state = hass.states.get(entity_id)
    if state is None:
        raise WeatherError(f"Weather entity not found: {entity_id}")
    if state.state in ("unavailable", "unknown"):
        raise WeatherError(f"Weather entity is {state.state}: {entity_id}")

    forecast_days = await _async_forecast(hass, entity_id, "daily")
    forecast_hours = await _async_forecast(hass, entity_id, "hourly")

    observed = state.last_updated
    if observed is not None and getattr(observed, "tzinfo", None) is None:
        observed = dt_util.as_utc(observed)

    return snapshot_from_state_and_forecast(
        entity_id=entity_id,
        state=state.state,
        attributes=dict(state.attributes),
        forecast_days=forecast_days,
        forecast_hours=forecast_hours,
        observed_at=observed,
        max_days=max_days,
        max_hours=max_hours,
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
