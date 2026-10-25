"""UI strings for the weather card (English + Polish)."""

from __future__ import annotations

from typing import Literal

WeatherLang = Literal["en", "pl"]

_WEEKDAY = {
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "pl": ("Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nd"),
}

_TODAY = {"en": "Today", "pl": "Dziś"}

_CONDITION = {
    "en": {
        "clear-night": "clear night",
        "cloudy": "cloudy",
        "fog": "fog",
        "hail": "hail",
        "lightning": "thunder",
        "lightning-rainy": "thunder rain",
        "partlycloudy": "partly cloudy",
        "pouring": "pouring",
        "rainy": "rainy",
        "snowy": "snowy",
        "snowy-rainy": "sleet",
        "sunny": "sunny",
        "windy": "windy",
        "windy-variant": "windy",
        "exceptional": "extreme",
    },
    "pl": {
        "clear-night": "bezchmurnie",
        "cloudy": "pochmurno",
        "fog": "mgła",
        "hail": "grad",
        "lightning": "burza",
        "lightning-rainy": "burza z deszczem",
        "partlycloudy": "częściowo pochmurno",
        "pouring": "ulewa",
        "rainy": "deszcz",
        "snowy": "śnieg",
        "snowy-rainy": "deszcz ze śniegiem",
        "sunny": "słonecznie",
        "windy": "wietrznie",
        "windy-variant": "wietrznie",
        "exceptional": "ekstremalnie",
    },
}

_DEW = {"en": "dew", "pl": "rosa"}
_GUST = {"en": "gust", "pl": "porywy"}
_HUM = {"en": "RH", "pl": "wilg"}
_PRES = {"en": "hPa", "pl": "hPa"}
_WIND = {"en": "wind", "pl": "wiatr"}

_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def weekday_short(lang: WeatherLang, monday_index: int) -> str:
    """``monday_index`` is ``datetime.weekday()`` (Mon=0)."""
    return _WEEKDAY[lang][monday_index % 7]


def today_label(lang: WeatherLang) -> str:
    return _TODAY[lang]


def condition_label(lang: WeatherLang, condition: str | None) -> str:
    if not condition:
        return "—"
    key = condition.lower().replace("_", "-")
    return _CONDITION[lang].get(key, key.replace("-", " "))


def dew_label(lang: WeatherLang) -> str:
    return _DEW[lang]


def gust_label(lang: WeatherLang) -> str:
    return _GUST[lang]


def humidity_label(lang: WeatherLang) -> str:
    return _HUM[lang]


def pressure_label(lang: WeatherLang) -> str:
    return _PRES[lang]


def wind_label(lang: WeatherLang) -> str:
    return _WIND[lang]

def compass_label(degrees: float) -> str:
    """8-point compass from meteorological wind-from bearing."""
    index = int((degrees % 360.0 + 22.5) // 45.0) % 8
    return _COMPASS[index]
