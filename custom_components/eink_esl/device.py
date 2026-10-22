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
    INK_SERVICE_UUID,
)

# LKESL app (lcdBleControl.vue) connect timing — keep in sync when porting fixes.
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
# Keep overall budgets short: hammering BlueZ with GATT connects has wedged HA Core.
CONNECT_WAIT_TIMEOUT_S = 60
# Manufacturer app: CREATE_CONN_TIMEOUT / CONNECT_RETRY_MAX / CONNECT_RETRY_DELAY.
CREATE_CONN_TIMEOUT_S = DEFAULT_CONNECT_TIMEOUT_S
CONNECT_RETRY_MAX = 2
CONNECT_RETRY_DELAY_S = 1.0
# One wait-for-ad slice (manufacturer SEARCH_TIMEOUT = 20s).
SEARCH_TIMEOUT_S = 15
# Diagnostic probe: few attempts only — must not storm BlueZ like a long upload.
PROBE_CONNECT_TIMEOUT_S = 35.0
PROBE_CONNECT_ATTEMPTS = 2
PROBE_POST_CONNECT_DELAY_S = 1.0
PROBE_LED_HOLD_S = 3.0
# Hard ceiling around bleak connect so a wedged BlueZ call cannot hang Core forever.
BLEAK_CONNECT_HARD_CAP_S = 22.0


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

    async def async_probe_connect(self) -> str:
        """Connect GATT like the Leeka app (no image) to verify the red LED.

        Aborts any in-flight upload, opens the link, waits for services, holds
        briefly so the tag LED stays on, then disconnects. Returns a human
        summary including advertised name (for ``D6633334`` / wrong-device checks).
        """
        self._upload_epoch += 1
        async with self._lock:
            return await self._async_probe_connect_locked()

    async def _async_probe_connect_locked(self) -> str:
        """GATT-only connect with the same connectable-ad retry rules as upload.

        Battery ads are often non-connectable: HA's Bleak wrapper only connects
        when the address is in the *current connectable* scanner set, so a single
        attempt right after a battery hit fails with \"connection slot / no
        scanner currently has it\" even though last ad was 2s ago.
        """
        from bleak import BleakClient

        ad_name = _advertised_name(self.hass, self.address)
        name_part = f", adv name={ad_name!r}" if ad_name else ""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + PROBE_CONNECT_TIMEOUT_S
        last_error: Exception | None = None
        attempt = 0

        self._fire_progress(
            "probing",
            message=(
                f"Probe: waiting for *connectable* ad from {self.address}"
                f"{name_part} (battery-only ads are not enough)…"
            ),
        )

        ble_device = await self._async_resolve_ble_device(deadline)
        while (
            ble_device is not None
            and loop.time() < deadline
            and attempt < PROBE_CONNECT_ATTEMPTS
        ):
            remaining = deadline - loop.time()
            attempt += 1
            connect_timeout = min(15.0, max(5.0, remaining))
            self._fire_progress(
                "connecting",
                message=(
                    f"Probe: connectable ad — GATT "
                    f"{attempt}/{PROBE_CONNECT_ATTEMPTS} "
                    f"(≤{connect_timeout:.0f}s, watch red LED)…"
                ),
            )
            client: object | None = None
            try:
                # Connect in the same breath as the live connectable ad.
                # Hard-capped: bare bleak timeouts have wedged HA Core before.
                client = BleakClient(ble_device)
                await asyncio.wait_for(
                    client.connect(timeout=connect_timeout),
                    timeout=min(BLEAK_CONNECT_HARD_CAP_S, connect_timeout + 2.0),
                )
                if not getattr(client, "is_connected", False):
                    raise HomeAssistantError(
                        f"Probe failed: connect returned but not connected "
                        f"({self.address})"
                    )

                # Same settle window as LKESL checkInkScreenDevice.
                await asyncio.sleep(PROBE_POST_CONNECT_DELAY_S)
                get_services = getattr(client, "get_services", None)
                if callable(get_services):
                    try:
                        await get_services()
                    except Exception:  # noqa: BLE001
                        _LOGGER.debug(
                            "probe get_services failed", exc_info=True
                        )

                services = getattr(client, "services", None)
                ink_ok = False
                if services is not None:
                    try:
                        ink_ok = (
                            services.get_service(INK_SERVICE_UUID) is not None
                        )
                    except Exception:  # noqa: BLE001
                        ink_ok = False

                self._fire_progress(
                    "probing",
                    message=(
                        f"Probe: connected — hold {PROBE_LED_HOLD_S:.0f}s "
                        f"(watch for red LED)…"
                    ),
                )
                await asyncio.sleep(PROBE_LED_HOLD_S)

                summary = (
                    f"Probe OK: connected to {self.address}{name_part}; "
                    f"ink GATT service "
                    f"{'FOUND' if ink_ok else 'MISSING'}. "
                    f"If the red LED lit, this is the right radio path."
                )
                self._fire_progress("done", message=summary)
                _LOGGER.info("%s", summary)
                return summary
            except TimeoutError as err:
                last_error = err
                _LOGGER.warning(
                    "Probe attempt %s/%s hard-timeout for %s (BlueZ may be wedged)",
                    attempt,
                    PROBE_CONNECT_ATTEMPTS,
                    self.address,
                )
            except Exception as err:  # noqa: BLE001
                last_error = err
                _LOGGER.info(
                    "Probe attempt %s/%s failed for %s: %s",
                    attempt,
                    PROBE_CONNECT_ATTEMPTS,
                    self.address,
                    err,
                )
                if not _is_retryable_connect_error(err):
                    raise HomeAssistantError(
                        f"Probe failed for {self.address}{name_part}: {err}"
                    ) from err
            finally:
                if client is not None and getattr(
                    client, "is_connected", False
                ):
                    try:
                        await client.disconnect()
                    except Exception:  # noqa: BLE001
                        _LOGGER.debug(
                            "probe disconnect failed", exc_info=True
                        )

            if attempt >= PROBE_CONNECT_ATTEMPTS:
                break
            # Do not reuse the same scanner entry — wait for a *new* connectable ad.
            remaining = deadline - loop.time()
            if remaining < 3.0:
                break
            self._fire_progress(
                "waiting",
                message=(
                    "Probe: connect missed — next connectable ad "
                    f"({_format_wait(remaining)}; "
                    f"attempt {attempt}/{PROBE_CONNECT_ATTEMPTS})…"
                ),
            )
            ble_device = await self._async_wait_for_advertisement(remaining)

        reason = _reachability_reason(self.hass, self.address)
        detail = f" ({reason})" if reason else ""
        if last_error is not None:
            raise HomeAssistantError(
                f"Probe failed for {self.address}{name_part}: {last_error}"
                f"{detail}"
            ) from last_error
        raise HomeAssistantError(
            f"Probe failed: no *connectable* advertisement for "
            f"{self.address}{name_part} within "
            f"{_format_wait(PROBE_CONNECT_TIMEOUT_S)}{detail}. "
            f"Battery ads alone cannot open GATT."
        )

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

            # Connect in the same breath as the live ad. Extra sleeps here
            # (LKESL stop-discovery settle / RSSI refine) let sleepy tags
            # leave the scanner set → "no scanner currently has it".
            burst_error: Exception | None = None
            for attempt in range(1, CONNECT_RETRY_MAX + 1):
                if should_abort():
                    raise TransferAborted()
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                # Need a full bleak attempt budget; shorter cancels → InProgress.
                connect_timeout = min(CREATE_CONN_TIMEOUT_S, remaining)
                if connect_timeout < 12.0:
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
                    establish_attempts=1,
                    close_stale_before_connect=False,
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
                        # InProgress needs longer than the 0.5s LKESL gap.
                        delay = (
                            2.0
                            if "in progress" in str(err).lower()
                            else CONNECT_RETRY_DELAY_S
                        )
                        await _async_sleep_abortable(delay, should_abort)
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

            # Burst exhausted — wait for the next advertisement window.
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

        Never connect from ``last_service_info`` or non-connectable ads: HA's
        Bleak wrapper re-queries ``async_scanner_devices_by_address(..., True)``
        inside ``connect()``. Battery/0x181A ads keep history fresh while the
        connectable current set is empty → \"connection slot / no scanner\".
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
                _LOGGER.info(
                    "Got connectable advertisement for %s — connecting",
                    self.address,
                )
                return ble_device

    async def _async_wait_for_advertisement(
        self,
        remaining: float,
        *,
        should_abort: Callable[[], bool] | None = None,
    ) -> object | None:
        """Active-scan until the next *connectable* ad; return its BLEDevice.

        Returning the device from the advertisement itself is critical: ESL tags
        drop out of the scanner's current set within a second, so a follow-up
        ``async_scanner_devices_by_address`` is often empty even after a hit.
        Non-connectable (battery) ads are ignored — they cannot open GATT.
        """
        # Short slices so a newer upload can abort without waiting SEARCH_TIMEOUT.
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
                    _is_connectable_service_info,
                    {"address": self.address},
                    BluetoothScanningMode.ACTIVE,
                    slice_s,
                )
            except TimeoutError:
                left -= slice_s
                continue
            device = getattr(service_info, "device", None)
            if device is not None:
                _LOGGER.debug(
                    "Got connectable advertisement for %s", self.address
                )
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


def _advertised_name(hass: HomeAssistant, address: str) -> str | None:
    """Best-effort local name from last advertisement (for wrong-device checks)."""
    for connectable in (True, False):
        try:
            info = bluetooth.async_last_service_info(
                hass, address, connectable=connectable
            )
        except Exception:  # noqa: BLE001
            info = None
        if info is None:
            continue
        name = (getattr(info, "name", None) or "").strip()
        if name and name.lower() not in {"unknown", "unnamed"}:
            return name
    return None


def _is_connectable_service_info(service_info: object) -> bool:
    """True when HA marks this advertisement as usable for GATT connect."""
    return bool(getattr(service_info, "connectable", False))


def _best_connectable_ble_device(hass: HomeAssistant, address: str) -> object | None:
    """BLEDevice from the strongest *connectable* scanner hit (not history).

    Must not fall back to ``connectable=False``: those devices satisfy battery
    sensors but HA refuses GATT with \"no scanner currently has it\".
    """
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
        "timed out",
        # Cancelling a mid-flight BlueZ connect leaves the adapter busy.
        "in progress",
        "org.bluez.error.inprogress",
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
