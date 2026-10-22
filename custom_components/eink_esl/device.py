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

from .ble import EinkBleClient, TransferAborted, TransferError, TransferProgress
from .ble.client import DEFAULT_CONNECT_TIMEOUT_S
from .const import (
    CONF_ADDRESS,
    CONF_PANEL_ID,
    DOMAIN,
    EVENT_TRANSFER_PROGRESS,
)
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

# Overall wait for a sleepy tag to advertise + a couple of GATT attempts.
CONNECT_WAIT_TIMEOUT_S = 60
CREATE_CONN_TIMEOUT_S = DEFAULT_CONNECT_TIMEOUT_S
CONNECT_RETRY_MAX = 2
CONNECT_RETRY_DELAY_S = 1.0
# Slice length for advertisement waits (also bounds abort latency).
SEARCH_TIMEOUT_S = 15


class EinkEslDevice:
    """One config entry / shelf label."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.address: str = entry.data[CONF_ADDRESS]
        self._lock = asyncio.Lock()
        # Bumped on every async_upload so an in-flight transfer can abort.
        self._upload_epoch = 0

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
        """Quantize ``image_bytes`` and push them to the tag.

        Starting a new upload bumps ``_upload_epoch`` so any in-flight transfer
        on this device sees abort and exits before this one takes the lock.
        """
        self._upload_epoch += 1
        epoch = self._upload_epoch

        def should_abort() -> bool:
            if self._upload_epoch != epoch:
                return True
            return abort() if abort is not None else False

        async with self._lock:
            if should_abort():
                raise HomeAssistantError("Transfer cancelled")
            try:
                await self._async_upload_locked(
                    image_bytes,
                    mode=mode,
                    fit=fit,
                    background=background,
                    should_abort=should_abort,
                )
            except TransferAborted as err:
                raise HomeAssistantError("Transfer cancelled") from err

    async def _async_upload_locked(
        self,
        image_bytes: bytes,
        *,
        mode: QuantizeMode,
        fit: FitMode,
        background: tuple[int, int, int],
        should_abort: Callable[[], bool],
    ) -> None:
        """Run encode + BLE connect/transfer while holding ``_lock``."""
        self._fire_progress("encoding", message="Encoding image…")
        encoded = await self.async_encode(
            image_bytes, mode=mode, fit=fit, background=background
        )
        if should_abort():
            raise TransferAborted()

        loop = asyncio.get_running_loop()
        deadline = loop.time() + CONNECT_WAIT_TIMEOUT_S
        last_error: Exception | None = None

        while True:
            if should_abort():
                raise TransferAborted()
            remaining = deadline - loop.time()
            if remaining <= 0:
                break

            ble_device = await self._async_resolve_ble_device(
                deadline, should_abort=should_abort
            )
            if ble_device is None:
                break

            burst_error: Exception | None = None
            for attempt in range(1, CONNECT_RETRY_MAX + 1):
                if should_abort():
                    raise TransferAborted()
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                connect_timeout = min(CREATE_CONN_TIMEOUT_S, remaining)
                if connect_timeout < 5.0:
                    break
                self._fire_progress(
                    "connecting",
                    message=(
                        f"Connecting… ({attempt}/{CONNECT_RETRY_MAX}, "
                        f"up to {connect_timeout:.0f}s)"
                    ),
                )
                held = ble_device

                def _ble_device_callback(
                    _held: object = held,
                ) -> object | None:
                    live = _best_connectable_ble_device(
                        self.hass, self.address
                    )
                    return live if live is not None else _held

                client = EinkBleClient(
                    self.address,
                    ble_device=ble_device,
                    ble_device_callback=_ble_device_callback,
                    connect_timeout_s=connect_timeout,
                )
                try:
                    await client.upload(
                        encoded.packed,
                        encoded.type_code,
                        abort=should_abort,
                        on_progress=self._on_transfer_progress,
                    )
                except TransferAborted:
                    raise
                except TransferError as err:
                    burst_error = err
                    last_error = err
                    _LOGGER.info(
                        "Connect attempt %s/%s failed for %s: %s",
                        attempt,
                        CONNECT_RETRY_MAX,
                        self.address,
                        err,
                    )
                    if not _is_retryable_connect_error(err):
                        raise HomeAssistantError(str(err)) from err
                    if attempt < CONNECT_RETRY_MAX:
                        await _async_sleep_abortable(
                            CONNECT_RETRY_DELAY_S, should_abort
                        )
                        ad_wait = min(
                            SEARCH_TIMEOUT_S, deadline - loop.time()
                        )
                        if ad_wait >= 3.0:
                            nxt = await self._async_wait_for_advertisement(
                                ad_wait, should_abort=should_abort
                            )
                            if nxt is not None:
                                ble_device = nxt
                    continue

                self._fire_progress("done", message="Sent.")
                _LOGGER.info(
                    "Uploaded %s B to %s (%s)",
                    len(encoded.packed),
                    self.address,
                    self.panel_label,
                )
                return

            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            if burst_error is not None and not _is_retryable_connect_error(
                burst_error
            ):
                raise HomeAssistantError(str(burst_error)) from burst_error
            self._fire_progress(
                "waiting",
                message=(
                    "Connect window missed — waiting for next advertisement "
                    f"({_format_wait(remaining)})…"
                ),
            )
            await self._async_wait_for_advertisement(
                remaining, should_abort=should_abort
            )

        if should_abort():
            raise TransferAborted()
        reason = _reachability_reason(self.hass, self.address)
        detail = f": {reason}" if reason else ""
        if last_error is not None:
            raise HomeAssistantError(
                f"{last_error} (gave up after "
                f"{_format_wait(CONNECT_WAIT_TIMEOUT_S)}){detail}"
            ) from last_error
        raise HomeAssistantError(
            f"ESL {self.address} not connectable within "
            f"{_format_wait(CONNECT_WAIT_TIMEOUT_S)}{detail}"
        )

    async def _async_resolve_ble_device(
        self,
        deadline: float,
        *,
        should_abort: Callable[[], bool] | None = None,
    ) -> object | None:
        """Return a BLEDevice from the *connectable* scanner set right now.

        Battery / 0x181A ads are often non-connectable: HA only opens GATT when
        the address is in the current connectable set (local adapter or proxy).
        """
        loop = asyncio.get_running_loop()

        while True:
            if should_abort is not None and should_abort():
                raise TransferAborted()
            ble_device = _best_connectable_ble_device(self.hass, self.address)
            if ble_device is not None:
                _LOGGER.info(
                    "Connectable scanner currently sees %s — connecting",
                    self.address,
                )
                return ble_device

            remaining = deadline - loop.time()
            if remaining <= 0:
                return None

            self._fire_progress(
                "waiting",
                message=(
                    "Waiting for connectable advertisement "
                    f"({_format_wait(remaining)})…"
                ),
            )
            _LOGGER.debug(
                "No connectable scanner hit for %s; waiting (%.1fs left)",
                self.address,
                remaining,
            )
            ble_device = await self._async_wait_for_advertisement(
                remaining, should_abort=should_abort
            )
            if ble_device is not None:
                # Prefer the connectable entry if the wait woke the scanner set.
                live = _best_connectable_ble_device(self.hass, self.address)
                chosen = live if live is not None else ble_device
                _LOGGER.info(
                    "Got advertisement for %s — connecting",
                    self.address,
                )
                return chosen

    async def _async_wait_for_advertisement(
        self,
        remaining: float,
        *,
        should_abort: Callable[[], bool] | None = None,
    ) -> object | None:
        """Active-scan until the next ad for this address; return its BLEDevice."""
        left = max(0.0, remaining)
        while left > 0:
            if should_abort is not None and should_abort():
                raise TransferAborted()
            slice_s = min(3.0, left, float(SEARCH_TIMEOUT_S))
            if slice_s < 0.5:
                return None
            try:
                service_info = await bluetooth.async_process_advertisements(
                    self.hass,
                    lambda _service_info: True,
                    {"address": self.address},
                    BluetoothScanningMode.ACTIVE,
                    slice_s,
                )
            except TimeoutError:
                left -= slice_s
                continue
            device = getattr(service_info, "device", None)
            if device is not None:
                _LOGGER.debug("Got advertisement for %s", self.address)
                return device
            left -= slice_s
        return None

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


def _format_wait(seconds: float) -> str:
    """Human wait remaining for progress UI (e.g. ``4m 12s``)."""
    total = max(1, int(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if secs == 0:
        return f"{minutes}m"
    return f"{minutes}m {secs}s"


async def _async_sleep_abortable(
    delay: float, should_abort: Callable[[], bool]
) -> None:
    """Sleep in short slices so a newer upload can cancel quickly."""
    loop = asyncio.get_running_loop()
    end = loop.time() + max(0.0, delay)
    while True:
        if should_abort():
            raise TransferAborted()
        left = end - loop.time()
        if left <= 0:
            return
        await asyncio.sleep(min(0.25, left))


def _best_connectable_ble_device(hass: HomeAssistant, address: str) -> object | None:
    """BLEDevice from the strongest *currently* seeing connectable scanner."""
    try:
        scanner_devices = bluetooth.async_scanner_devices_by_address(
            hass, address, connectable=True
        )
    except AttributeError:
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
    """True when waiting for another advertisement is worth it."""
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
        "timed out",
        "in progress",
    )
    return any(needle in text for needle in needles)


def _reachability_reason(hass: HomeAssistant, address: str) -> str | None:
    """Best-effort human explanation when no scanner can see the tag."""
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
