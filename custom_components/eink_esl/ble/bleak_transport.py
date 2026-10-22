"""Bleak-backed ``InkTransport`` for the ink GATT characteristic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..const import INK_CHARACTERISTIC_UUID, INK_SERVICE_UUID
from .errors import TransferError

_LOGGER = logging.getLogger(__name__)

# LKESL checkInkScreenDevice / checkLcdDevice: wait 1s after connect before
# getBLEDeviceServices — BlueZ/sleepy tags often need that settle window.
_POST_CONNECT_GATT_DELAY_S = 1.0


class BleakInkTransport:
    """Notify queue + write helpers on an already-connected Bleak client."""

    def __init__(
        self,
        client: Any,
        *,
        write_with_response: bool,
        write_without_response: bool,
    ) -> None:
        self._client = client
        self._supports_write_with_response = write_with_response
        self._supports_write_without_response = write_without_response
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._closed = False

    @classmethod
    async def open(cls, client: Any) -> BleakInkTransport:
        """Resolve the ink characteristic, enable notify, return a transport."""
        await asyncio.sleep(_POST_CONNECT_GATT_DELAY_S)

        # Force a live service list (do not trust a cached empty/partial table).
        get_services = getattr(client, "get_services", None)
        if callable(get_services):
            try:
                await get_services()
            except Exception:  # noqa: BLE001 - some bleak backends already resolved
                _LOGGER.debug("get_services() after connect failed", exc_info=True)

        try:
            service = client.services.get_service(INK_SERVICE_UUID)
        except Exception as err:  # noqa: BLE001 - Bleak version differences
            raise TransferError("Ink service not found on device") from err
        if service is None:
            raise TransferError("Ink service not found on device")

        characteristic = service.get_characteristic(INK_CHARACTERISTIC_UUID)
        if characteristic is None:
            raise TransferError("Ink characteristic not found on device")

        props = set(characteristic.properties)
        transport = cls(
            client,
            write_with_response="write" in props,
            write_without_response="write-without-response" in props,
        )
        await client.start_notify(INK_CHARACTERISTIC_UUID, transport._on_notify)
        _LOGGER.info(
            "Ink characteristic ready (write=%s withoutResponse=%s notify=%s)",
            "write" in props,
            "write-without-response" in props,
            "notify" in props,
        )
        return transport

    @property
    def supports_write_with_response(self) -> bool:
        return self._supports_write_with_response

    @property
    def supports_write_without_response(self) -> bool:
        return self._supports_write_without_response

    def drain_notifications(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def write(self, data: bytes, *, response: bool) -> None:
        await self._client.write_gatt_char(
            INK_CHARACTERISTIC_UUID,
            data,
            response=response,
        )

    async def next_notification(self, timeout_s: float) -> bytes:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout_s)
        except TimeoutError as err:
            raise TimeoutError("No ACK") from err

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._client.stop_notify(INK_CHARACTERISTIC_UUID)
        except Exception:  # noqa: BLE001 - disconnect path must not raise
            _LOGGER.debug("stop_notify failed", exc_info=True)

    def _on_notify(self, _sender: Any, data: bytearray) -> None:
        if not data:
            return
        self._queue.put_nowait(bytes(data))
