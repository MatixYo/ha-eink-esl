"""GATT connect via Home Assistant's Bleak wrapper.

Works with local adapters and ESPHome ``bluetooth_proxy`` — both are routed by
HA. Do not bypass with a direct BlueZ backend: that only talks to the host
adapter and breaks proxy-backed transfers.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

from .errors import TransferError

_LOGGER = logging.getLogger(__name__)

__all__ = ["async_gatt_connect"]


async def async_gatt_connect(
    ble_device: Any,
    *,
    timeout_s: float = 15.0,
) -> Any:
    """Connect GATT through HA's ``BleakClient`` (proxy-aware)."""
    try:
        from bleak import BleakClient
    except ImportError as err:
        raise TransferError("bleak is required for Bluetooth transfers") from err

    timeout = max(5.0, min(30.0, float(timeout_s)))
    hard_cap = timeout + 2.0
    try:
        client = BleakClient(ble_device, timeout=timeout)
    except TypeError:
        client = BleakClient(ble_device)

    _LOGGER.info(
        "Connecting via HA BleakClient (timeout=%.0fs hard_cap=%.0fs)",
        timeout,
        hard_cap,
    )
    try:
        await _async_invoke_connect(client, hard_cap)
    except TimeoutError as err:
        await _async_best_effort_disconnect(client)
        raise TransferError(
            f"BLE connect timed out after {hard_cap:.0f}s"
        ) from err
    except Exception as err:
        await _async_best_effort_disconnect(client)
        raise TransferError(
            f"BLE connect failed: {type(err).__name__}: {err}"
        ) from err

    if not getattr(client, "is_connected", False):
        raise TransferError("BLE connect returned but client is not connected")
    return client


async def _async_invoke_connect(client: Any, hard_cap: float) -> None:
    """Call ``client.connect`` across bleak versions (``pair`` may be required)."""
    kwargs: dict[str, Any] = {}
    try:
        params = inspect.signature(client.connect).parameters
    except (TypeError, ValueError):
        params = {}
    if "pair" in params:
        param = params["pair"]
        if param.default is inspect.Parameter.empty:
            kwargs["pair"] = False
    await asyncio.wait_for(client.connect(**kwargs), timeout=hard_cap)


async def _async_best_effort_disconnect(client: Any) -> None:
    try:
        if getattr(client, "is_connected", False):
            await client.disconnect()
    except Exception:  # noqa: BLE001
        _LOGGER.debug("disconnect after failed connect", exc_info=True)
