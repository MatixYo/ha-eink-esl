"""Resolve HA device registry ids to ``EinkEslDevice`` instances."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .device import EinkEslDevice, async_get_device


def devices_from_ids(
    hass: HomeAssistant, device_ids: list[str]
) -> list[EinkEslDevice]:
    """Map Home Assistant device ids to runtime ESL devices."""
    registry = dr.async_get(hass)
    devices: list[EinkEslDevice] = []
    for device_id in device_ids:
        entry_id = entry_id_for_device(hass, registry, device_id)
        devices.append(async_get_device(hass, entry_id))
    if not devices:
        raise HomeAssistantError("No E-Ink ESL device targeted")
    return devices


def entry_id_for_device(
    hass: HomeAssistant,
    registry: dr.DeviceRegistry,
    device_id: str,
) -> str:
    """Return the config entry id for an ESL device registry entry."""
    device = registry.async_get(device_id)
    if device is None:
        raise HomeAssistantError(f"Unknown device id: {device_id}")
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            return entry.entry_id
    raise HomeAssistantError(f"Device {device_id} is not an E-Ink ESL label")
