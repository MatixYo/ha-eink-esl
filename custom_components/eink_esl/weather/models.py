"""Pure weather snapshot types (no Home Assistant dependency)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DayForecast:
    """One daily forecast entry (high/low when available)."""

    when: datetime | None
    condition: str | None
    temperature: float | None
    templow: float | None
    humidity: float | None
    precipitation: float | None
    wind_speed: float | None


@dataclass(frozen=True, slots=True)
class WeatherSnapshot:
    """Current conditions plus a short daily strip for the renderer."""

    entity_id: str
    condition: str | None
    temperature: float | None
    humidity: float | None
    dew_point: float | None
    pressure: float | None
    wind_speed: float | None
    wind_bearing: float | str | None
    cloud_coverage: float | None
    uv_index: float | None
    temperature_unit: str
    wind_speed_unit: str
    pressure_unit: str
    precipitation_unit: str
    attribution: str | None
    days: tuple[DayForecast, ...]
    observed_at: datetime | None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        # HA forecasts use ISO-8601; fromisoformat accepts offset with ':' .
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def day_forecast_from_mapping(entry: dict[str, Any]) -> DayForecast:
    """Build a ``DayForecast`` from a ``weather.get_forecasts`` list item."""
    return DayForecast(
        when=_parse_datetime(entry.get("datetime")),
        condition=str(entry["condition"]) if entry.get("condition") else None,
        temperature=_as_float(entry.get("temperature")),
        templow=_as_float(entry.get("templow")),
        humidity=_as_float(entry.get("humidity")),
        precipitation=_as_float(entry.get("precipitation")),
        wind_speed=_as_float(entry.get("wind_speed")),
    )


def snapshot_from_state_and_forecast(
    *,
    entity_id: str,
    state: str,
    attributes: dict[str, Any],
    forecast_days: list[dict[str, Any]],
    observed_at: datetime | None = None,
    max_days: int = 5,
) -> WeatherSnapshot:
    """Assemble a snapshot from entity state attrs + daily forecast rows."""
    condition = state if state not in ("unknown", "unavailable", "") else None
    days = tuple(
        day_forecast_from_mapping(row)
        for row in forecast_days[: max(0, max_days)]
    )
    return WeatherSnapshot(
        entity_id=entity_id,
        condition=condition,
        temperature=_as_float(attributes.get("temperature")),
        humidity=_as_float(attributes.get("humidity")),
        dew_point=_as_float(attributes.get("dew_point")),
        pressure=_as_float(attributes.get("pressure")),
        wind_speed=_as_float(attributes.get("wind_speed")),
        wind_bearing=attributes.get("wind_bearing"),
        cloud_coverage=_as_float(attributes.get("cloud_coverage")),
        uv_index=_as_float(attributes.get("uv_index")),
        temperature_unit=str(attributes.get("temperature_unit") or "°C"),
        wind_speed_unit=str(attributes.get("wind_speed_unit") or "km/h"),
        pressure_unit=str(attributes.get("pressure_unit") or "hPa"),
        precipitation_unit=str(attributes.get("precipitation_unit") or "mm"),
        attribution=(
            str(attributes["attribution"])
            if attributes.get("attribution")
            else None
        ),
        days=days,
        observed_at=observed_at,
    )
