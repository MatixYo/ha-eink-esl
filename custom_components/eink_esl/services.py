"""Home Assistant services for image upload and BLE diagnostics."""

from __future__ import annotations

import asyncio
import logging
from typing import Final

import voluptuous as vol

from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .background import BACKGROUND_RGB
from .const import DOMAIN
from .device_lookup import devices_from_ids
from .image_input import decode_image_payload

_LOGGER = logging.getLogger(__name__)

SERVICE_UPLOAD_IMAGE: Final = "upload_image"
SERVICE_PROBE_CONNECT: Final = "probe_connect"

ATTR_IMAGE: Final = "image"
ATTR_FIT: Final = "fit"
ATTR_MODE: Final = "mode"
ATTR_BACKGROUND: Final = "background"

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
        vol.Optional(ATTR_BACKGROUND, default="white"): vol.In(
            ["white", "black"]
        ),
    }
)

PROBE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.ensure_list,
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.data.setdefault(DOMAIN, {}).get("_services"):
        return

    async def async_upload_image(call: ServiceCall) -> None:
        # Base64 of phone photos can be multi‑MB — keep it off the event loop.
        image_bytes = await asyncio.to_thread(
            decode_image_payload, hass, call.data[ATTR_IMAGE]
        )
        fit = call.data[ATTR_FIT]
        mode = call.data[ATTR_MODE]
        background = BACKGROUND_RGB[call.data[ATTR_BACKGROUND]]
        for device in devices_from_ids(hass, call.data[CONF_DEVICE_ID]):
            await device.async_upload(
                image_bytes, mode=mode, fit=fit, background=background
            )

    async def async_probe_connect(call: ServiceCall) -> dict:
        """GATT-only probe (Leeka-style connect) for red-LED / wrong-device checks."""
        messages: list[str] = []
        for device in devices_from_ids(hass, call.data[CONF_DEVICE_ID]):
            messages.append(await device.async_probe_connect())
        return {"messages": messages}

    hass.services.async_register(
        DOMAIN, SERVICE_UPLOAD_IMAGE, async_upload_image, schema=UPLOAD_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PROBE_CONNECT,
        async_probe_connect,
        schema=PROBE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.data[DOMAIN]["_services"] = True
    _LOGGER.debug("Registered %s services", DOMAIN)


async def async_unload_services(hass: HomeAssistant) -> None:
    """Remove domain services when the last entry unloads."""
    if not hass.data.get(DOMAIN, {}).get("_services"):
        return
    hass.services.async_remove(DOMAIN, SERVICE_UPLOAD_IMAGE)
    hass.services.async_remove(DOMAIN, SERVICE_PROBE_CONNECT)
    if DOMAIN in hass.data:
        hass.data[DOMAIN].pop("_services", None)
