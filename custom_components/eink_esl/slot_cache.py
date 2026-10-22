"""Per-label last frame cache in Home Assistant Store (not the browser)."""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.slots"
_STORE_DATA_KEY = "_slot_store"
_STORE_CACHE_KEY = "_slot_data"


def _empty() -> dict[str, Any]:
    return {"slots": {}}


async def async_get_store(hass: HomeAssistant) -> Store:
    """Return the shared Store instance for slot metadata + PNG payloads."""
    hass.data.setdefault(DOMAIN, {})
    store = hass.data[DOMAIN].get(_STORE_DATA_KEY)
    if store is None:
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        hass.data[DOMAIN][_STORE_DATA_KEY] = store
    return store


async def async_load_data(hass: HomeAssistant) -> dict[str, Any]:
    """Load slot data once into ``hass.data`` (subsequent calls reuse it)."""
    hass.data.setdefault(DOMAIN, {})
    cached = hass.data[DOMAIN].get(_STORE_CACHE_KEY)
    if cached is not None:
        return cached
    store = await async_get_store(hass)
    data = await store.async_load()
    if not isinstance(data, dict) or "slots" not in data:
        data = _empty()
    hass.data[DOMAIN][_STORE_CACHE_KEY] = data
    return data


async def async_get_slot(
    hass: HomeAssistant, entry_id: str
) -> dict[str, Any] | None:
    """Return the cached slot dict for a config entry, or ``None``."""
    data = await async_load_data(hass)
    slot = data.get("slots", {}).get(entry_id)
    return slot if isinstance(slot, dict) and slot.get("content_b64") else None


async def async_save_slot(
    hass: HomeAssistant,
    entry_id: str,
    *,
    png_bytes: bytes,
    width: int,
    height: int,
    fit: str = "stretch",
    mode: str = "nearest",
    background: str = "white",
    label: str = "",
    weather_entity_id: str | None = None,
) -> dict[str, Any]:
    """Persist a panel-sized PNG + encode settings for ``entry_id``."""
    data = await async_load_data(hass)
    previous = data.get("slots", {}).get(entry_id) or {}
    weather = weather_entity_id
    if weather is None and isinstance(previous, dict):
        weather = previous.get("weather_entity_id")

    slot = {
        "content_b64": base64.b64encode(png_bytes).decode("ascii"),
        "content_type": "image/png",
        "width": width,
        "height": height,
        "fit": fit,
        "mode": mode,
        "background": background,
        "label": label or previous.get("label", ""),
        "weather_entity_id": weather,
        "saved_at": datetime.now(tz=UTC).isoformat(),
    }
    data.setdefault("slots", {})[entry_id] = slot
    store = await async_get_store(hass)
    await store.async_save(data)
    _LOGGER.debug(
        "Saved slot cache for entry %s (%s×%s, %s B)",
        entry_id,
        width,
        height,
        len(png_bytes),
    )
    return slot


async def async_save_slot_meta(
    hass: HomeAssistant,
    entry_id: str,
    *,
    weather_entity_id: str | None = None,
    label: str | None = None,
) -> None:
    """Update non-image fields without replacing the PNG."""
    data = await async_load_data(hass)
    slots = data.setdefault("slots", {})
    slot = slots.get(entry_id)
    if not isinstance(slot, dict):
        slot = {
            "content_b64": "",
            "content_type": "image/png",
            "width": 0,
            "height": 0,
            "fit": "stretch",
            "mode": "nearest",
            "background": "white",
            "label": "",
            "weather_entity_id": None,
        }
        slots[entry_id] = slot
    if weather_entity_id is not None:
        slot["weather_entity_id"] = weather_entity_id
    if label is not None:
        slot["label"] = label
    slot["saved_at"] = datetime.now(tz=UTC).isoformat()
    store = await async_get_store(hass)
    await store.async_save(data)


def slot_to_api_payload(slot: dict[str, Any]) -> dict[str, Any]:
    """Shape a stored slot for the sidebar HTTP response."""
    return {
        "width": slot.get("width"),
        "height": slot.get("height"),
        "fit": slot.get("fit", "stretch"),
        "mode": slot.get("mode", "nearest"),
        "background": slot.get("background", "white"),
        "label": slot.get("label") or "",
        "weather_entity_id": slot.get("weather_entity_id"),
        "saved_at": slot.get("saved_at"),
        "content_type": slot.get("content_type", "image/png"),
        "content": slot.get("content_b64", ""),
    }
