"""WebSocket commands for the sidebar panel (preview from Python encode)."""

from __future__ import annotations

import base64
import logging

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .background import BACKGROUND_RGB
from .const import DOMAIN
from .device_lookup import devices_from_ids
from .image_input import decode_image_payload

_LOGGER = logging.getLogger(__name__)

_WS_KEY = "_websocket"


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    """Register websocket commands once."""
    hass.data.setdefault(DOMAIN, {})
    if hass.data[DOMAIN].get(_WS_KEY):
        return
    websocket_api.async_register_command(hass, ws_preview)
    hass.data[DOMAIN][_WS_KEY] = True
    _LOGGER.debug("Registered %s websocket commands", DOMAIN)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/preview",
        vol.Required(CONF_DEVICE_ID): str,
        vol.Required("image"): str,
        vol.Optional("fit", default="contain"): vol.In(
            ["contain", "cover", "stretch"]
        ),
        vol.Optional("mode", default="floyd-steinberg"): vol.In(
            ["nearest", "floyd-steinberg"]
        ),
        vol.Optional("background", default="white"): vol.In(["white", "black"]),
    }
)
@websocket_api.async_response
async def ws_preview(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Encode with the same Python path as upload; return a PNG preview."""
    try:
        image_bytes = decode_image_payload(hass, msg["image"])
        device = devices_from_ids(hass, [msg[CONF_DEVICE_ID]])[0]
        png, width, height = await device.async_preview_png(
            image_bytes,
            mode=msg["mode"],
            fit=msg["fit"],
            background=BACKGROUND_RGB[msg["background"]],
        )
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "preview_failed", str(err))
        return
    except Exception as err:  # noqa: BLE001 - surface unexpected encode errors
        _LOGGER.exception("Preview failed")
        connection.send_error(msg["id"], "preview_failed", str(err))
        return

    connection.send_result(
        msg["id"],
        {
            "width": width,
            "height": height,
            "content_type": "image/png",
            "content": base64.b64encode(png).decode("ascii"),
        },
    )
