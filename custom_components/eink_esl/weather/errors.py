"""Domain errors for weather fetch / render."""

from __future__ import annotations


class WeatherError(Exception):
    """Weather entity missing, unsupported, or render failed."""
