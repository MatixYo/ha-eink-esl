"""Unit tests for weather snapshot parsing (no Home Assistant)."""

from __future__ import annotations

from datetime import datetime, timezone

from custom_components.eink_esl.weather.models import (
    snapshot_from_state_and_forecast,
)


def test_snapshot_from_met_no_shaped_payload() -> None:
    """Fixture shaped like weather.forecast_home + daily get_forecasts."""
    attributes = {
        "temperature": 8.1,
        "dew_point": 4.3,
        "temperature_unit": "°C",
        "humidity": 78,
        "cloud_coverage": 3.9,
        "uv_index": 0.0,
        "pressure": 1018.7,
        "pressure_unit": "hPa",
        "wind_bearing": 247.2,
        "wind_speed": 9.7,
        "wind_speed_unit": "km/h",
        "precipitation_unit": "mm",
        "attribution": "Weather forecast from met.no",
        "friendly_name": "Forecast Home",
    }
    forecast = [
        {
            "datetime": "2026-10-23T10:00:00+00:00",
            "condition": "partlycloudy",
            "temperature": 15.0,
            "templow": 5.0,
            "humidity": 60,
            "precipitation": 0.0,
            "wind_speed": 16.2,
        },
        {
            "datetime": "2026-10-24T10:00:00+00:00",
            "condition": "rainy",
            "temperature": 10.9,
            "templow": 5.1,
            "precipitation": 6.5,
            "wind_speed": 26.6,
        },
    ]
    snap = snapshot_from_state_and_forecast(
        entity_id="weather.forecast_home",
        state="clear-night",
        attributes=attributes,
        forecast_days=forecast,
        observed_at=datetime(2026, 10, 22, 19, 4, tzinfo=timezone.utc),
        max_days=5,
    )
    assert snap.condition == "clear-night"
    assert snap.temperature == 8.1
    assert snap.humidity == 78
    assert snap.temperature_unit == "°C"
    assert len(snap.days) == 2
    assert snap.days[0].condition == "partlycloudy"
    assert snap.days[0].temperature == 15.0
    assert snap.days[0].templow == 5.0
    assert snap.days[1].precipitation == 6.5
    assert snap.days[0].when == datetime(
        2026, 10, 23, 10, 0, tzinfo=timezone.utc
    )


def test_unknown_state_clears_condition() -> None:
    snap = snapshot_from_state_and_forecast(
        entity_id="weather.x",
        state="unknown",
        attributes={},
        forecast_days=[],
    )
    assert snap.condition is None
    assert snap.days == ()
