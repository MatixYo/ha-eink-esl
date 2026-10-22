"""Home Assistant services for upload and clear."""

from __future__ import annotations

import logging
from typing import Final

import voluptuous as vol

from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .device import EinkEslDevice, async_get_device
from .image_input import decode_image_payload
from .protocol import CLEAR_BLACK, CLEAR_WHITE

_LOGGER = logging.getLogger(__name__)

SERVICE_UPLOAD_IMAGE: Final = "upload_image"
SERVICE_CLEAR_SCREEN: Final = "clear_screen"

ATTR_IMAGE: Final = "image"
ATTR_COLOR: Final = "color"
ATTR_FIT: Final = "fit"
ATTR_MODE: Final = "mode"

COLOR_MAP = {
    "white": CLEAR_WHITE,
    "black": CLEAR_BLACK,
}

UPLOAD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.ensure_list,
        vol.Required(ATTR_IMAGE): cv.string,
        vol.Optional(ATTR_FIT, default="contain"): vol.In(
            ["contain", "cover", "stretch"]
        ),
        vol.Optional(ATTR_MODE, default="floyd-steinberg"): vol.In(
            ["nearest", "floyd-steinberg"]
        ),
    }
)

CLEAR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.ensure_list,
        vol.Optional(ATTR_COLOR, default="white"): vol.In(["white", "black"]),
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.data.setdefault(DOMAIN, {}).get("_services"):
        return

    async def async_upload_image(call: ServiceCall) -> None:
        image_bytes = decode_image_payload(hass, call.data[ATTR_IMAGE])
        fit = call.data[ATTR_FIT]
        mode = call.data[ATTR_MODE]
        for device in _devices_from_call(hass, call):
            await device.async_upload(image_bytes, mode=mode, fit=fit)

    async def async_clear_screen(call: ServiceCall) -> None:
        color = COLOR_MAP[call.data[ATTR_COLOR]]
        for device in _devices_from_call(hass, call):
            await device.async_clear(color)

    hass.services.async_register(
        DOMAIN, SERVICE_UPLOAD_IMAGE, async_upload_image, schema=UPLOAD_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_SCREEN, async_clear_screen, schema=CLEAR_SCHEMA
    )
    hass.data[DOMAIN]["_services"] = True
    _LOGGER.debug("Registered %s services", DOMAIN)


async def async_unload_services(hass: HomeAssistant) -> None:
    """Remove domain services when the last entry unloads."""
    if not hass.data.get(DOMAIN, {}).get("_services"):
        return
    hass.services.async_remove(DOMAIN, SERVICE_UPLOAD_IMAGE)
    hass.services.async_remove(DOMAIN, SERVICE_CLEAR_SCREEN)
    if DOMAIN in hass.data:
        hass.data[DOMAIN].pop("_services", None)


def _devices_from_call(
    hass: HomeAssistant, call: ServiceCall
) -> list[EinkEslDevice]:
    device_ids: list[str] = call.data[CONF_DEVICE_ID]
    registry = dr.async_get(hass)
    devices: list[EinkEslDevice] = []
    for device_id in device_ids:
        entry_id = _entry_id_for_device(hass, registry, device_id)
        devices.append(async_get_device(hass, entry_id))
    if not devices:
        raise HomeAssistantError("No E-Ink ESL device targeted")
    return devices


def _entry_id_for_device(
    hass: HomeAssistant,
    registry: dr.DeviceRegistry,
    device_id: str,
) -> str:
    device = registry.async_get(device_id)
    if device is None:
        raise HomeAssistantError(f"Unknown device id: {device_id}")
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            return entry.entry_id
    raise HomeAssistantError(f"Device {device_id} is not an E-Ink ESL label")
