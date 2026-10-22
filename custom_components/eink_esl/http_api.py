"""HTTP API for the sidebar panel (preview uses POST — large images over WS hang)."""

from __future__ import annotations

import base64
import logging

from aiohttp import web
import voluptuous as vol

from homeassistant.components.http import HomeAssistantView
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .background import BACKGROUND_RGB
from .const import DOMAIN
from .device_lookup import devices_from_ids
from .image_input import decode_image_payload

_LOGGER = logging.getLogger(__name__)

_HTTP_KEY = "_http_api"

PREVIEW_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Required("image"): cv.string,
        vol.Optional("fit", default="contain"): vol.In(
            ["contain", "cover", "stretch"]
        ),
        vol.Optional("mode", default="floyd-steinberg"): vol.In(
            ["nearest", "floyd-steinberg"]
        ),
        vol.Optional("background", default="white"): vol.In(["white", "black"]),
    }
)


@callback
def async_setup_http(hass: HomeAssistant) -> None:
    """Register HTTP views once."""
    hass.data.setdefault(DOMAIN, {})
    if hass.data[DOMAIN].get(_HTTP_KEY):
        return
    hass.http.register_view(EinkEslPreviewView)
    hass.data[DOMAIN][_HTTP_KEY] = True
    _LOGGER.debug("Registered %s HTTP API", DOMAIN)


class EinkEslPreviewView(HomeAssistantView):
    """POST /api/eink_esl/preview — quantized PNG from the Python encoder."""

    url = f"/api/{DOMAIN}/preview"
    name = f"api:{DOMAIN}:preview"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            payload = PREVIEW_SCHEMA(await request.json())
        except vol.Invalid as err:
            return self.json_message(str(err), status_code=400)
        except Exception:  # noqa: BLE001
            return self.json_message("Invalid JSON body", status_code=400)

        try:
            image_bytes = decode_image_payload(hass, payload["image"])
            device = devices_from_ids(hass, [payload[CONF_DEVICE_ID]])[0]
            png, width, height = await device.async_preview_png(
                image_bytes,
                mode=payload["mode"],
                fit=payload["fit"],
                background=BACKGROUND_RGB[payload["background"]],
            )
        except HomeAssistantError as err:
            return self.json_message(str(err), status_code=400)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Preview failed")
            return self.json_message("Preview failed", status_code=500)

        return self.json(
            {
                "width": width,
                "height": height,
                "content_type": "image/png",
                "content": base64.b64encode(png).decode("ascii"),
            }
        )
