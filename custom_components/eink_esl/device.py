"""Per-label runtime: encode images and run short-lived BLE transfers."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothScanningMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .ble import EinkBleClient, TransferError, TransferProgress
from .const import CONF_ADDRESS, CONF_PANEL_ID, DOMAIN, EVENT_TRANSFER_PROGRESS
from .image import (
    EncodedImage,
    FitMode,
    ImageError,
    QuantizeMode,
    prepare_for_panel,
    preview_png_bytes,
)
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

    async def async_encode(
        self,
        image_bytes: bytes,
        *,
        mode: QuantizeMode = "floyd-steinberg",
        fit: FitMode = "contain",
        background: tuple[int, int, int] = (255, 255, 255),
    ) -> EncodedImage:
        """Fit / quantize / pack without opening BLE (shared by preview + upload)."""
        panel = panel_by_id(self.panel_id)
        started = time.perf_counter()
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
        _LOGGER.info(
            "Encoded %s B → %s B for %s in %.0f ms (%s/%s)",
            len(image_bytes),
            len(encoded.packed),
            panel.id,
            (time.perf_counter() - started) * 1000,
            fit,
            mode,
        )
        return encoded

    async def async_preview_png(
        self,
        image_bytes: bytes,
        *,
        mode: QuantizeMode = "floyd-steinberg",
        fit: FitMode = "contain",
        background: tuple[int, int, int] = (255, 255, 255),
    ) -> tuple[bytes, int, int]:
        """Return PNG bytes of the quantized frame plus panel size."""
        encoded = await self.async_encode(
            image_bytes, mode=mode, fit=fit, background=background
        )
        try:
            png = await asyncio.to_thread(
                preview_png_bytes,
                encoded.preview_rgba,
                encoded.width,
                encoded.height,
            )
        except ImageError as err:
            raise HomeAssistantError(str(err)) from err
        return png, encoded.width, encoded.height

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
            self._fire_progress("encoding", message="Encoding image…")
            encoded = await self.async_encode(
                image_bytes, mode=mode, fit=fit, background=background
            )

            loop = asyncio.get_running_loop()
            deadline = loop.time() + CONNECT_WAIT_TIMEOUT_S

            while True:
                client = await self._async_ble_client(deadline)
                try:
                    await client.upload(
                        encoded.packed,
                        encoded.type_code,
                        abort=abort,
                        on_progress=self._on_transfer_progress,
                    )
                except TransferError as err:
                    remaining = deadline - loop.time()
                    if remaining <= 0 or not _is_retryable_connect_error(err):
                        raise HomeAssistantError(str(err)) from err
                    remaining_s = max(1, int(remaining))
                    self._fire_progress(
                        "waiting",
                        message=(
                            "Bluetooth busy / tag left scan — "
                            f"retrying ({remaining_s}s)…"
                        ),
                    )
                    _LOGGER.info(
                        "Connect/upload failed for %s (%s); retrying (%.1fs left)",
                        self.address,
                        err,
                        remaining,
                    )
                    await self._async_wait_for_advertisement(remaining)
                    continue

                self._fire_progress("done", message="Sent.")
                _LOGGER.info(
                    "Uploaded %s B to %s (%s)",
                    len(encoded.packed),
                    self.address,
                    self.panel_label,
                )
                return

    async def _async_ble_client(self, deadline: float) -> EinkBleClient:
        """Resolve a *currently scanned* connectable path before connecting.

        ``async_ble_device_from_address`` can return a history-only device.
        Connecting then fails with "no backend with an available connection
        slot … no scanner currently has it in its discovered devices". Wait
        for a live scanner hit instead.
        """
        loop = asyncio.get_running_loop()
        saw_wait = False

        while True:
            ble_device = _current_connectable_ble_device(self.hass, self.address)
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
                    f"Waiting for tag advertisement ({remaining_s}s)…"
                ),
            )
            _LOGGER.debug(
                "No live scanner path for %s yet; retrying (%.1fs left)",
                self.address,
                remaining,
            )
            await self._async_wait_for_advertisement(remaining)

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

    async def _async_wait_for_advertisement(self, remaining: float) -> None:
        """Active-scan until the next ad for this address or ``remaining`` expires."""
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


def _current_connectable_ble_device(hass: HomeAssistant, address: str) -> object | None:
    """BLEDevice from a scanner that *currently* sees the address (not history).

    History-only devices make ``connect`` fail with "no scanner currently has
    it in its discovered devices" even when the last ad was seconds ago.
    """
    try:
        scanner_devices = bluetooth.async_scanner_devices_by_address(
            hass, address, connectable=True
        )
    except AttributeError:
        # Older HA — best effort from the bluetooth manager cache.
        try:
            return bluetooth.async_ble_device_from_address(
                hass, address, connectable=True
            )
        except Exception:  # noqa: BLE001
            return None
    except Exception:  # noqa: BLE001
        return None

    if not scanner_devices:
        return None
    best = max(
        scanner_devices,
        key=lambda item: getattr(item.advertisement, "rssi", -999) or -999,
    )
    return best.ble_device


def _is_retryable_connect_error(err: Exception) -> bool:
    """True for slot exhaustion / missing live path — worth waiting for a new ad."""
    text = str(err).lower()
    needles = (
        "connection slot",
        "out of connection slots",
        "no backend",
        "not found",
        "no scanner currently",
        "esp_gatt_conn",
        "disconnected",
        "timeout",
    )
    return any(needle in text for needle in needles)


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
