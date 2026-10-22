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

from .ble import EinkBleClient, TransferError, TransferProgress
from .const import CONF_ADDRESS, CONF_PANEL_ID, DOMAIN, EVENT_TRANSFER_PROGRESS
from .image import FitMode, ImageError, QuantizeMode, prepare_for_panel
from .protocol import DEFAULT_PANEL_ID, ProtocolError, panel_by_id

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
        background: tuple[int, int, int] = (255, 255, 255),
        abort: Callable[[], bool] | None = None,
    ) -> None:
        """Quantize ``image_bytes`` and push them to the tag."""
        async with self._lock:
            panel = panel_by_id(self.panel_id)
            self._fire_progress("encoding", message="Encoding image…")
            try:
                encoded = await asyncio.to_thread(
                    prepare_for_panel,
                    image_bytes,
                    panel,
                    mode=mode,
                    fit=fit,
                    background=background,
                )
            except (ImageError, ProtocolError) as err:
                raise HomeAssistantError(str(err)) from err

            client = await self._async_ble_client()
            try:
                await client.upload(
                    encoded.packed,
                    encoded.type_code,
                    abort=abort,
                    on_progress=self._on_transfer_progress,
                )
            except TransferError as err:
                raise HomeAssistantError(str(err)) from err

            self._fire_progress("done", message="Sent.")
            _LOGGER.info(
                "Uploaded %s B to %s (%s)",
                len(encoded.packed),
                self.address,
                panel.label,
            )

    async def _async_ble_client(self) -> EinkBleClient:
        """Resolve a connectable path, retrying for up to CONNECT_WAIT_TIMEOUT_S.

        HA can see a fresh advertisement but still return no ``BLEDevice`` when
        the adapter has no free connection slot. A single
        ``async_process_advertisements`` return is not enough — keep retrying.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CONNECT_WAIT_TIMEOUT_S
        saw_wait = False

        while True:
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is not None:
                self._fire_progress("connecting", message="Connecting…")
                return EinkBleClient(self.address, ble_device=ble_device)

            remaining = deadline - loop.time()
            if remaining <= 0:
                break

            saw_wait = True
            remaining_s = max(1, int(remaining))
            self._fire_progress(
                "waiting",
                message=(
                    f"Waiting for tag / free Bluetooth slot ({remaining_s}s)…"
                ),
            )
            _LOGGER.debug(
                "No connectable BLEDevice for %s yet; retrying (%.1fs left)",
                self.address,
                remaining,
            )
            # Short active-scan slices: ads often arrive immediately while slots
            # stay busy, which previously aborted the whole wait early.
            slice_s = min(5, max(1, int(remaining)))
            try:
                await bluetooth.async_process_advertisements(
                    self.hass,
                    lambda _service_info: True,
                    {"address": self.address, "connectable": True},
                    BluetoothScanningMode.ACTIVE,
                    slice_s,
                )
            except TimeoutError:
                pass
            await asyncio.sleep(0.25)

        # Last resort: BlueZ can sometimes connect by address alone.
        if _address_recently_seen(self.hass, self.address):
            _LOGGER.warning(
                "No HA BLEDevice for %s after %ss (slots?); trying address-only",
                self.address,
                CONNECT_WAIT_TIMEOUT_S,
            )
            self._fire_progress("connecting", message="Connecting…")
            return EinkBleClient(self.address, ble_device=None)

        reason = _reachability_reason(self.hass, self.address)
        detail = f": {reason}" if reason else ""
        if saw_wait:
            raise HomeAssistantError(
                f"ESL {self.address} not connectable within "
                f"{CONNECT_WAIT_TIMEOUT_S}s{detail}"
            )
        raise HomeAssistantError(
            f"ESL {self.address} is not reachable via Bluetooth{detail}"
        )

    def _on_transfer_progress(self, progress: TransferProgress) -> None:
        labels = {
            "clear": "Clearing…",
            "start": "Starting transfer…",
            "chunks": "Sending image…",
            "display": "Refreshing display…",
        }
        message = labels.get(progress.phase, progress.phase)
        if progress.phase == "chunks" and progress.total:
            message = f"Sending {progress.sent}/{progress.total}…"
        self._fire_progress(
            progress.phase,
            sent=progress.sent,
            total=progress.total,
            message=message,
        )

    def _fire_progress(
        self,
        phase: str,
        *,
        sent: int = 0,
        total: int = 0,
        message: str = "",
    ) -> None:
        self.hass.bus.async_fire(
            EVENT_TRANSFER_PROGRESS,
            {
                "address": self.address,
                "entry_id": self.entry.entry_id,
                "phase": phase,
                "sent": sent,
                "total": total,
                "message": message,
            },
        )


def _address_recently_seen(hass: HomeAssistant, address: str) -> bool:
    """True if HA has a recent advertisement for this address."""
    try:
        if bluetooth.async_address_present(hass, address, connectable=True):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        return (
            bluetooth.async_last_service_info(hass, address, connectable=True)
            is not None
        )
    except Exception:  # noqa: BLE001
        return False


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
