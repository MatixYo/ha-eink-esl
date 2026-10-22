"""HTTP API for the sidebar panel (preview POST — large images over WS hang)."""

from __future__ import annotations

import asyncio
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
from .slot_cache import (
    async_get_slot,
    async_save_slot,
    async_save_slot_meta,
    slot_to_api_payload,
)
from .weather.errors import WeatherError
from .weather.fetch import list_weather_entity_ids
from .weather.generate import async_generate_weather_png

_LOGGER = logging.getLogger(__name__)

# Survives DOMAIN pop on last-entry unload so re-register does not crash setup.
_HTTP_REGISTERED = f"{DOMAIN}_http_registered"

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

WEATHER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Required("entity_id"): cv.entity_id,
    }
)

SLOT_PUT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
        vol.Optional("image"): cv.string,
        vol.Optional("fit", default="stretch"): vol.In(
            ["contain", "cover", "stretch"]
        ),
        vol.Optional("mode", default="nearest"): vol.In(
            ["nearest", "floyd-steinberg"]
        ),
        vol.Optional("background", default="white"): vol.In(["white", "black"]),
        vol.Optional("label", default=""): cv.string,
        vol.Optional("weather_entity_id"): vol.Any(None, cv.entity_id),
        vol.Optional("width"): vol.Coerce(int),
        vol.Optional("height"): vol.Coerce(int),
    }
)


@callback
def async_setup_http(hass: HomeAssistant) -> None:
    """Register HTTP views once per Home Assistant process."""
    if hass.data.get(_HTTP_REGISTERED):
        return
    for view in (
        EinkEslPreviewView,
        EinkEslWeatherView,
        EinkEslSlotView,
    ):
        try:
            hass.http.register_view(view)
        except Exception:  # noqa: BLE001 - duplicate route after reload
            _LOGGER.exception(
                "Could not register %s HTTP view %s", DOMAIN, view
            )
    hass.data[_HTTP_REGISTERED] = True
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
            image_bytes = await asyncio.to_thread(
                decode_image_payload, hass, payload["image"]
            )
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


class EinkEslWeatherView(HomeAssistantView):
    """POST /api/eink_esl/weather — render current weather as a panel PNG."""

    url = f"/api/{DOMAIN}/weather"
    name = f"api:{DOMAIN}:weather"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            payload = WEATHER_SCHEMA(await request.json())
        except vol.Invalid as err:
            return self.json_message(str(err), status_code=400)
        except Exception:  # noqa: BLE001
            return self.json_message("Invalid JSON body", status_code=400)

        entity_id = payload["entity_id"]
        if not entity_id.startswith("weather."):
            return self.json_message(
                "entity_id must be a weather entity", status_code=400
            )

        try:
            device = devices_from_ids(hass, [payload[CONF_DEVICE_ID]])[0]
            png, width, height = await async_generate_weather_png(
                hass, device, entity_id
            )
            await async_save_slot(
                hass,
                device.entry.entry_id,
                png_bytes=png,
                width=width,
                height=height,
                fit="stretch",
                mode="nearest",
                background="white",
                label=entity_id,
                weather_entity_id=entity_id,
            )
        except (HomeAssistantError, WeatherError) as err:
            return self.json_message(str(err), status_code=400)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Weather render failed")
            return self.json_message("Weather render failed", status_code=500)

        return self.json(
            {
                "width": width,
                "height": height,
                "entity_id": entity_id,
                "weather_entities": list_weather_entity_ids(hass),
                "content_type": "image/png",
                "content": base64.b64encode(png).decode("ascii"),
            }
        )


class EinkEslSlotView(HomeAssistantView):
    """GET/PUT /api/eink_esl/slot — last frame for a label (HA Store)."""

    url = f"/api/{DOMAIN}/slot"
    name = f"api:{DOMAIN}:slot"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        device_id = request.query.get("device_id")
        if not device_id:
            return self.json_message("device_id is required", status_code=400)
        try:
            device = devices_from_ids(hass, [device_id])[0]
            slot = await async_get_slot(hass, device.entry.entry_id)
        except HomeAssistantError as err:
            return self.json_message(str(err), status_code=400)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Slot load failed")
            return self.json_message("Slot load failed", status_code=500)

        if slot is None:
            return self.json({"empty": True})
        return self.json(slot_to_api_payload(slot))

    async def put(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            payload = SLOT_PUT_SCHEMA(await request.json())
        except vol.Invalid as err:
            return self.json_message(str(err), status_code=400)
        except Exception:  # noqa: BLE001
            return self.json_message("Invalid JSON body", status_code=400)

        try:
            device = devices_from_ids(hass, [payload[CONF_DEVICE_ID]])[0]
            entry_id = device.entry.entry_id
            image = payload.get("image")
            if image:
                png = await asyncio.to_thread(
                    decode_image_payload, hass, image
                )
                if payload.get("width") and payload.get("height"):
                    width = int(payload["width"])
                    height = int(payload["height"])
                else:
                    width, height = await asyncio.to_thread(_png_size, png)
                slot = await async_save_slot(
                    hass,
                    entry_id,
                    png_bytes=png,
                    width=width,
                    height=height,
                    fit=payload["fit"],
                    mode=payload["mode"],
                    background=payload["background"],
                    label=payload.get("label") or "",
                    weather_entity_id=payload.get("weather_entity_id"),
                )
            else:
                await async_save_slot_meta(
                    hass,
                    entry_id,
                    weather_entity_id=payload.get("weather_entity_id"),
                    label=payload.get("label"),
                )
                slot = await async_get_slot(hass, entry_id)
                if slot is None:
                    return self.json({"empty": True})
        except HomeAssistantError as err:
            return self.json_message(str(err), status_code=400)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Slot save failed")
            return self.json_message("Slot save failed", status_code=500)

        return self.json(slot_to_api_payload(slot))


def _png_size(png: bytes) -> tuple[int, int]:
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(png)) as image:
        return image.size
