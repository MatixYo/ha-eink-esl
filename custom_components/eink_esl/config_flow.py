"""Config flow for E-Ink ESL (multi-device: one entry per label)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import config_validation as cv

from .const import CONF_PANEL_ID, DOMAIN

# Temporary default until panel catalog lands (matches web app default).
DEFAULT_PANEL_ID = "bwry-350"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_PANEL_ID, default=DEFAULT_PANEL_ID): cv.string,
    }
)


class EinkEslConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for E-Ink ESL."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual entry by Bluetooth address (discovery comes later)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"ESL {address}",
                data={
                    CONF_ADDRESS: address,
                    CONF_PANEL_ID: user_input.get(CONF_PANEL_ID, DEFAULT_PANEL_ID),
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
