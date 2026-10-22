"""Bluetooth discovery helpers for Leeka-compatible ESL tags."""

from __future__ import annotations

from typing import Any

from .const import BATTERY_SERVICE_UUID
from .protocol import battery_percent_from_service_data

_BATTERY_UUID = BATTERY_SERVICE_UUID.lower()


def is_esl_candidate(discovery_info: Any) -> bool:
    """Return True if advertisement looks like a Leeka-style ESL tag.

    The ink GATT service is not advertised. Tags put battery bytes in
    Environmental Sensing (0x181A) service data — see the protocol doc.
    """
    service_data = getattr(discovery_info, "service_data", None) or {}
    for uuid, data in service_data.items():
        if str(uuid).lower() != _BATTERY_UUID:
            continue
        if data is None:
            continue
        raw = bytes(data)
        if battery_percent_from_service_data(raw) is not None:
            return True

    service_uuids = getattr(discovery_info, "service_uuids", None) or ()
    return any(str(uuid).lower() == _BATTERY_UUID for uuid in service_uuids)


def discovery_title(discovery_info: Any) -> str:
    """Human title for a discovered ESL advertisement."""
    name = (getattr(discovery_info, "name", None) or "").strip()
    address = getattr(discovery_info, "address", "")
    if name and name.lower() not in {"unknown", "unnamed"}:
        return f"{name} ({address})"
    return f"ESL {address}"


def battery_from_discovery(discovery_info: Any) -> int | None:
    """Extract battery % from advertisement service data when present."""
    service_data = getattr(discovery_info, "service_data", None) or {}
    for uuid, data in service_data.items():
        if str(uuid).lower() != _BATTERY_UUID or data is None:
            continue
        percent = battery_percent_from_service_data(bytes(data))
        if percent is not None:
            return percent
    return None
