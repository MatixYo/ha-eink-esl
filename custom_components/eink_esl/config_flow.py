"""Config flow for E-Ink ESL (discovery + manual address, one entry per label)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import CONF_PANEL_ID, DOMAIN
from .discovery import discovery_title, is_esl_candidate
from .protocol import DEFAULT_PANEL_ID, PANELS

MANUAL_ENTRY = "__manual__"

PANEL_CHOICES = {panel.id: panel.label for panel in PANELS}


def _panel_schema(default: str = DEFAULT_PANEL_ID) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_PANEL_ID, default=default): vol.In(PANEL_CHOICES),
        }
    )


class EinkEslConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for E-Ink ESL."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}
        self._address: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EinkEslOptionsFlow:
        """Return the options flow for panel selection."""
        return EinkEslOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a Bluetooth advertisement match from the manifest."""
        if not is_esl_candidate(discovery_info):
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self._address = discovery_info.address.upper()
        title = discovery_title(discovery_info)
        self.context["title_placeholders"] = {"name": title}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered label, then pick the panel model."""
        assert self._address is not None
        if user_input is not None:
            return await self.async_step_panel()

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=self.context.get("title_placeholders", {}),
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a discovered device or switch to manual address entry."""
        errors: dict[str, str] = {}
        # Prefer unique_id, but also data[address] — older entries may lack unique_id
        # and would otherwise reappear under Add device forever.
        current_ids = {
            unique_id.upper()
            for unique_id in self._async_current_ids(include_ignore=False)
            if unique_id
        }
        current_ids.update(
            str(entry.data.get(CONF_ADDRESS, "")).strip().upper()
            for entry in self._async_current_entries(include_ignore=False)
            if entry.data.get(CONF_ADDRESS)
        )
        self._discovered_devices = {}
        for discovery_info in async_discovered_service_info(self.hass, True):
            address = discovery_info.address.upper()
            if address in current_ids or address in self._discovered_devices:
                continue
            if not is_esl_candidate(discovery_info):
                continue
            self._discovered_devices[address] = discovery_title(discovery_info)

        if user_input is not None:
            selection = user_input[CONF_ADDRESS]
            if selection == MANUAL_ENTRY:
                return await self.async_step_manual()
            address = selection.strip().upper()
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._address = address
            return await self.async_step_panel()

        choices = dict(self._discovered_devices)
        choices[MANUAL_ENTRY] = "Enter Bluetooth address manually…"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(choices)}
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual Bluetooth address entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            if len(address) < 11:
                errors["base"] = "invalid_address"
            else:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                self._address = address
                return await self.async_step_panel()

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): cv.string}),
            errors=errors,
        )

    async def async_step_panel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the panel model / type code for this label."""
        assert self._address is not None
        if user_input is not None:
            panel_id = user_input[CONF_PANEL_ID]
            title = (
                discovery_title(self._discovery_info)
                if self._discovery_info is not None
                else f"ESL {self._address}"
            )
            return self.async_create_entry(
                title=title,
                data={CONF_ADDRESS: self._address},
                options={CONF_PANEL_ID: panel_id},
            )

        return self.async_show_form(
            step_id="panel",
            data_schema=_panel_schema(),
            description_placeholders={"address": self._address},
        )


class EinkEslOptionsFlow(OptionsFlow):
    """Options flow to change the panel model for an existing label."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage panel model."""
        entry = self.config_entry
        current = entry.options.get(
            CONF_PANEL_ID, entry.data.get(CONF_PANEL_ID, DEFAULT_PANEL_ID)
        )
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={CONF_PANEL_ID: user_input[CONF_PANEL_ID]},
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_panel_schema(default=current),
            description_placeholders={
                "address": entry.data.get(CONF_ADDRESS, ""),
            },
        )
