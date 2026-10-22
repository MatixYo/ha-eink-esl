"""Connect → transfer → disconnect client (LED off after every attempt)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from ..protocol import CLEAR_BLACK, CLEAR_WHITE, DEFAULT_PAYLOAD_BYTES
from .bleak_transport import BleakInkTransport
from .errors import TransferError
from .progress import TransferProgress
from .session import EinkSession, ProgressCallback

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

# Re-export for callers that only import client.
__all__ = [
    "CLEAR_BLACK",
    "CLEAR_WHITE",
    "EinkBleClient",
    "TransferProgress",
]


class EinkBleClient:
    """Short-lived BLE link for one ESL address.

    Opens GATT only for the duration of ``clear`` / ``upload``, then always
    disconnects so the tag LED turns off.
    """

    def __init__(
        self,
        address: str,
        *,
        ble_device: Any | None = None,
        payload_size: int = DEFAULT_PAYLOAD_BYTES,
    ) -> None:
        self._address = address
        self._ble_device = ble_device
        self._payload_size = payload_size

    @property
    def address(self) -> str:
        return self._address

    async def clear(
        self,
        color: int = CLEAR_WHITE,
        *,
        abort: Callable[[], bool] | None = None,
    ) -> None:
        await self._with_session(
            lambda session: session.clear(color, abort=abort)
        )

    async def upload(
        self,
        image: bytes,
        device_type: int,
        *,
        abort: Callable[[], bool] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        await self._with_session(
            lambda session: session.upload(
                image,
                device_type,
                abort=abort,
                on_progress=on_progress,
            )
        )

    async def _with_session(
        self, operation: Callable[[EinkSession], Awaitable[T]]
    ) -> T:
        try:
            from bleak import BleakClient
        except ImportError as err:
            raise TransferError(
                "bleak is required for Bluetooth transfers"
            ) from err

        target = self._ble_device if self._ble_device is not None else self._address
        client = BleakClient(target)
        transport: BleakInkTransport | None = None
        try:
            _LOGGER.debug("Connecting to %s", self._address)
            await client.connect()
            if not client.is_connected:
                raise TransferError(f"Could not connect to {self._address}")
            transport = await BleakInkTransport.open(client)
            session = EinkSession(transport, payload_size=self._payload_size)
            return await operation(session)
        finally:
            # Disconnect even on failure so the shelf-label LED turns off.
            if transport is not None:
                await transport.close()
            if client.is_connected:
                _LOGGER.debug("Disconnecting from %s", self._address)
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("disconnect failed", exc_info=True)
