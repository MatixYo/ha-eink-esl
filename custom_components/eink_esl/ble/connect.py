"""GATT connect helpers — HA scanner path + BlueZ fallback.

Home Assistant's ``HaBleakClientWrapper.connect`` re-queries
``async_scanner_devices_by_address(..., connectable=True)``. Sleepy ESL tags
often leave that *current* set within <1s while history still says
\"last advertisement 1s ago\", which raises the familiar connection-slot error
immediately (no radio attempt). A direct platform backend connect using the
advertisement's ``BLEDevice`` (BlueZ path in ``details``) can still succeed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .errors import TransferError

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "async_gatt_connect",
    "is_ha_scanner_slot_error",
]


def is_ha_scanner_slot_error(err: BaseException) -> bool:
    """True when HA refused connect before talking to the radio."""
    text = str(err).lower()
    return any(
        needle in text
        for needle in (
            "connection slot",
            "no backend with an available connection slot",
            "no scanner currently has it",
            "out of connection slots",
        )
    )


async def async_gatt_connect(
    address: str,
    ble_device: Any,
    *,
    timeout_s: float = 15.0,
    allow_bluez_fallback: bool = True,
) -> Any:
    """Connect GATT; fall back to raw BlueZ backend on HA scanner-slot miss.

    Returns a connected client-like object (HA ``BleakClient`` or platform
    backend) suitable for ``BleakInkTransport.open``.
    """
    timeout = max(5.0, min(15.0, float(timeout_s)))
    hard_cap = min(22.0, timeout + 2.0)

    try:
        return await _async_connect_ha_wrapper(ble_device, timeout, hard_cap)
    except Exception as err:
        if not allow_bluez_fallback or not is_ha_scanner_slot_error(err):
            raise
        _LOGGER.warning(
            "HA scanner has no live connectable path for %s (%s) — "
            "trying direct BlueZ backend with advertisement device",
            address,
            err,
        )

    return await _async_connect_platform_backend(
        address, ble_device, timeout, hard_cap
    )


async def _async_connect_ha_wrapper(
    ble_device: Any, timeout: float, hard_cap: float
) -> Any:
    try:
        from bleak import BleakClient
    except ImportError as err:
        raise TransferError("bleak is required for Bluetooth transfers") from err

    client = BleakClient(ble_device)
    _LOGGER.info(
        "Connecting via HA BleakClient (timeout=%.0fs hard_cap=%.0fs)",
        timeout,
        hard_cap,
    )
    try:
        await asyncio.wait_for(client.connect(timeout=timeout), timeout=hard_cap)
    except TimeoutError:
        await _async_best_effort_disconnect(client)
        raise
    return client


async def _async_connect_platform_backend(
    address: str,
    ble_device: Any,
    timeout: float,
    hard_cap: float,
) -> Any:
    """Instantiate the OS bleak backend directly (skips HaBleakClientWrapper)."""
    try:
        from bleak.backends.client import get_platform_client_backend_type
    except ImportError as err:
        raise TransferError(
            f"No platform BLE backend available for {address}"
        ) from err

    backend = get_platform_client_backend_type()
    client_cls = backend[0] if isinstance(backend, tuple) else backend
    _LOGGER.info(
        "Connecting via direct backend %s for %s (timeout=%.0fs)",
        getattr(client_cls, "__name__", client_cls),
        address,
        timeout,
    )
    client = client_cls(ble_device)
    try:
        await asyncio.wait_for(client.connect(timeout=timeout), timeout=hard_cap)
    except TimeoutError:
        await _async_best_effort_disconnect(client)
        raise
    if not getattr(client, "is_connected", False):
        raise TransferError(f"Direct BlueZ connect returned not connected ({address})")
    return client


async def _async_best_effort_disconnect(client: Any) -> None:
    try:
        if getattr(client, "is_connected", False):
            await client.disconnect()
    except Exception:  # noqa: BLE001
        _LOGGER.debug("disconnect after failed connect", exc_info=True)
