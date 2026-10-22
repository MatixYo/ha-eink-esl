"""The E-Ink ESL integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import Platform

from .const import CONF_ADDRESS, CONF_PANEL_ID, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Platforms will be registered as they are implemented (sensor, button, …).
PLATFORMS: list[Platform] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one ESL device from a config entry."""
    from homeassistant.helpers import device_registry as dr

    from .device import EinkEslDevice
    from .protocol import DEFAULT_PANEL_ID, panel_by_id
    from .services import async_setup_services

    hass.data.setdefault(DOMAIN, {})

    device = EinkEslDevice(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = device

    panel_id = entry.options.get(
        CONF_PANEL_ID, entry.data.get(CONF_PANEL_ID, DEFAULT_PANEL_ID)
    )
    panel = panel_by_id(panel_id)
    address = entry.data[CONF_ADDRESS]
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, address)},
        connections={(dr.CONNECTION_BLUETOOTH, address)},
        name=entry.title,
        manufacturer="Leeka-compatible",
        model=panel.label,
    )

    await async_setup_services(hass)

    from .http_api import async_setup_http
    from .panel import async_register_panel

    async_setup_http(hass)
    await async_register_panel(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.debug(
        "Set up %s entry %s (address=%s panel=%s)",
        DOMAIN,
        entry.entry_id,
        address,
        panel.id,
    )
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options (panel model) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from .panel import async_unregister_panel
    from .services import async_unload_services

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        remaining = [
            key
            for key in hass.data.get(DOMAIN, {})
            if key not in {"_services", "_panel_registered", "_http_api", "_websocket"}
        ]
        if not remaining:
            await async_unload_services(hass)
            await async_unregister_panel(hass)
            hass.data.pop(DOMAIN, None)
    return unload_ok
