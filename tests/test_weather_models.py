"""Unit tests for weather snapshot parsing (no Home Assistant)."""

from __future__ import annotations

from datetime import datetime, timezone

from custom_components.eink_esl.weather.models import (
    snapshot_from_state_and_forecast,
)


def test_snapshot_from_met_no_shaped_payload() -> None:
    """Fixture shaped like weather.forecast_home + daily/hourly forecasts."""
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
            "datetime": "2026-10-25T10:00:00+00:00",
            "condition": "rainy",
            "temperature": 10.9,
            "templow": 8.7,
            "humidity": 65,
            "precipitation": 6.2,
            "wind_speed": 29.5,
            "wind_bearing": 177.4,
        },
        {
            "datetime": "2026-10-26T10:00:00+00:00",
            "condition": "partlycloudy",
            "temperature": 15.0,
            "templow": 5.0,
            "humidity": 60,
            "precipitation": 0.0,
            "wind_speed": 16.2,
            "wind_bearing": 200,
        },
    ]
    hours = [
        {
            "datetime": "2026-10-25T12:00:00+00:00",
            "condition": "rainy",
            "temperature": 10.0,
            "humidity": 65,
            "precipitation": 1.0,
            "wind_speed": 28.1,
            "wind_bearing": 174.6,
            "cloud_coverage": 100.0,
        }
    ]
    snap = snapshot_from_state_and_forecast(
        entity_id="weather.forecast_home",
        state="rainy",
        attributes=attributes,
        forecast_days=forecast,
        forecast_hours=hours,
        observed_at=datetime(2026, 10, 25, 11, 0, tzinfo=timezone.utc),
        max_days=4,
    )
    assert snap.condition == "rainy"
    assert snap.temperature == 8.1
    assert snap.dew_point == 4.3
    assert len(snap.days) == 2
    assert snap.days[0].condition == "rainy"
    assert snap.days[0].wind_bearing == 177.4
    assert len(snap.hours) == 1
    assert snap.hours[0].precipitation == 1.0


def test_unknown_state_clears_condition() -> None:
    snap = snapshot_from_state_and_forecast(
        entity_id="weather.x",
        state="unknown",
        attributes={},
        forecast_days=[],
    )
    assert snap.condition is None
    assert snap.days == ()
    assert snap.hours == ()
