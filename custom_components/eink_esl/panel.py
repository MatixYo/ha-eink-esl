"""Register the E-Ink ESL sidebar panel."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .manifest_version import INTEGRATION_VERSION

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "eink-esl"
PANEL_STATIC_URL = f"/{DOMAIN}_static"
PANEL_FILENAME = "eink-esl-panel.js"
_PANEL_KEY = "_panel_registered"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Serve static frontend and add a sidebar entry (once)."""
    hass.data.setdefault(DOMAIN, {})
    if hass.data[DOMAIN].get(_PANEL_KEY):
        return

    static_dir = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                PANEL_STATIC_URL, str(static_dir), cache_headers=False
            )
        ]
    )

    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name="eink-esl-panel",
        sidebar_title="E-Ink ESL",
        sidebar_icon="mdi:tablet",
        module_url=f"{PANEL_STATIC_URL}/{PANEL_FILENAME}?v={INTEGRATION_VERSION}",
        embed_iframe=False,
        require_admin=False,
    )
    hass.data[DOMAIN][_PANEL_KEY] = True
    _LOGGER.debug("Registered sidebar panel at /%s", PANEL_URL_PATH)


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar panel when the last config entry unloads."""
    if not hass.data.get(DOMAIN, {}).get(_PANEL_KEY):
        return
    frontend.async_remove_panel(hass, PANEL_URL_PATH)
    hass.data[DOMAIN].pop(_PANEL_KEY, None)
    _LOGGER.debug("Removed sidebar panel /%s", PANEL_URL_PATH)
