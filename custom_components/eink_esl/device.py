"""Per-label runtime: encode images and run short-lived BLE transfers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothScanningMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .ble import EinkBleClient, TransferError
from .const import CONF_ADDRESS, CONF_PANEL_ID, DOMAIN
from .image import FitMode, ImageError, QuantizeMode, prepare_for_panel
from .protocol import (
    CLEAR_WHITE,
    DEFAULT_PANEL_ID,
    ProtocolError,
    panel_by_id,
)

_LOGGER = logging.getLogger(__name__)

# Protocol doc only covers packet ACK timing (2s × 3), not advertising intervals.
# Buttonless tags sleep between ads; wait this long for the next one before connect.
CONNECT_WAIT_TIMEOUT_S = 30


class EinkEslDevice:
    """One config entry / shelf label."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.address: str = entry.data[CONF_ADDRESS]
        self._lock = asyncio.Lock()

    @property
    def panel_id(self) -> str:
        """Panel model id from options (falls back to entry data / default)."""
        return self.entry.options.get(
            CONF_PANEL_ID,
            self.entry.data.get(CONF_PANEL_ID, DEFAULT_PANEL_ID),
        )

    @property
    def panel_label(self) -> str:
        return panel_by_id(self.panel_id).label

    async def async_upload(
        self,
        image_bytes: bytes,
        *,
        mode: QuantizeMode = "floyd-steinberg",
        fit: FitMode = "contain",
        abort: Callable[[], bool] | None = None,
    ) -> None:
        """Quantize ``image_bytes`` and push them to the tag."""
        async with self._lock:
            panel = panel_by_id(self.panel_id)
            try:
                encoded = await asyncio.to_thread(
                    prepare_for_panel,
                    image_bytes,
                    panel,
                    mode=mode,
                    fit=fit,
                )
            except (ImageError, ProtocolError) as err:
                raise HomeAssistantError(str(err)) from err

            client = await self._async_ble_client()
            try:
                await client.upload(
                    encoded.packed,
                    encoded.type_code,
                    abort=abort,
                )
            except TransferError as err:
                raise HomeAssistantError(str(err)) from err

            _LOGGER.info(
                "Uploaded %s B to %s (%s)",
                len(encoded.packed),
                self.address,
                panel.label,
            )

    async def async_clear(self, color: int = CLEAR_WHITE) -> None:
        """Clear the tag to white or black."""
        async with self._lock:
            client = await self._async_ble_client()
            try:
                await client.clear(color)
            except TransferError as err:
                raise HomeAssistantError(str(err)) from err
            _LOGGER.info("Cleared %s (color=0x%02x)", self.address, color)

    async def _async_ble_client(self) -> EinkBleClient:
        """Resolve a connectable BLE device, waiting for the next advertisement."""
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            _LOGGER.info(
                "Waiting up to %ss for %s to advertise again",
                CONNECT_WAIT_TIMEOUT_S,
                self.address,
            )
            try:
                await bluetooth.async_process_advertisements(
                    self.hass,
                    lambda _service_info: True,
                    {"address": self.address, "connectable": True},
                    BluetoothScanningMode.ACTIVE,
                    CONNECT_WAIT_TIMEOUT_S,
                )
            except TimeoutError as err:
                reason = _reachability_reason(self.hass, self.address)
                raise HomeAssistantError(
                    f"ESL {self.address} did not advertise within "
                    f"{CONNECT_WAIT_TIMEOUT_S}s"
                    + (f": {reason}" if reason else "")
                ) from err

            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )

        if ble_device is None:
            reason = _reachability_reason(self.hass, self.address)
            raise HomeAssistantError(
                f"ESL {self.address} is not reachable via Bluetooth"
                + (f": {reason}" if reason else "")
            )
        return EinkBleClient(self.address, ble_device=ble_device)


def _reachability_reason(hass: HomeAssistant, address: str) -> str | None:
    """Best-effort human explanation when the adapter cannot see the tag."""
    try:
        from homeassistant.components.bluetooth import (
            BluetoothReachabilityIntent,
            async_address_reachability_diagnostics,
        )

        return async_address_reachability_diagnostics(
            hass, address, BluetoothReachabilityIntent.CONNECTION
        )
    except Exception:  # noqa: BLE001 - optional API / older HA
        return None


def async_get_device(hass: HomeAssistant, entry_id: str) -> EinkEslDevice:
    """Return runtime data for a config entry id."""
    try:
        return hass.data[DOMAIN][entry_id]
    except KeyError as err:
        raise HomeAssistantError(
            f"E-Ink ESL device {entry_id} is not loaded"
        ) from err
