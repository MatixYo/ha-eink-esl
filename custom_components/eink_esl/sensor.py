"""Advertisement-based sensors for ESL shelf labels."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .discovery import battery_from_discovery
from .device import async_get_device

if TYPE_CHECKING:
    from .device import EinkEslDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up battery sensor for one ESL label."""
    device = async_get_device(hass, entry.entry_id)
    async_add_entities([EinkBatterySensor(device)])


class EinkBatterySensor(SensorEntity):
    """Battery % from Environmental Sensing (0x181A) advertisement data."""

    _attr_has_entity_name = True
    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, device: EinkEslDevice) -> None:
        self._device = device
        address = device.address
        self._attr_unique_id = f"{address}_battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(dr.CONNECTION_BLUETOOTH, address)},
        )
        self._attr_native_value: int | None = None
        self._attr_available = False

    async def async_added_to_hass(self) -> None:
        """Seed from last ad, then follow live advertisements."""
        await super().async_added_to_hass()
        address = self._device.address
        for connectable in (True, False):
            try:
                info = bluetooth.async_last_service_info(
                    self.hass, address, connectable=connectable
                )
            except Exception:  # noqa: BLE001 - optional / older HA
                info = None
            if info is not None and self._apply_service_info(info):
                self.async_write_ha_state()
                break

        # Dict matcher (same shape as device.py wait-for-ad) — widely compatible.
        self.async_on_remove(
            bluetooth.async_register_callback(
                self.hass,
                self._async_handle_bluetooth_event,
                {"address": address},
                BluetoothScanningMode.ACTIVE,
            )
        )

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: BluetoothServiceInfoBleak,
        _change: BluetoothChange,
    ) -> None:
        if self._apply_service_info(service_info):
            self.async_write_ha_state()

    def _apply_service_info(self, service_info: BluetoothServiceInfoBleak) -> bool:
        """Update state from an advertisement; True if battery value changed."""
        percent = battery_from_discovery(service_info)
        if percent is None:
            return False
        # Firmware reports 0–100; clamp bad ads.
        percent = max(0, min(100, int(percent)))
        changed = (
            not self._attr_available
            or self._attr_native_value != percent
        )
        self._attr_native_value = percent
        self._attr_available = True
        if changed:
            _LOGGER.debug(
                "Battery for %s → %s%%",
                self._device.address,
                percent,
            )
        return changed
