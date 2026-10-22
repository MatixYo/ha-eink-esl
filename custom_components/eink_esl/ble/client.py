"""Connect → transfer → disconnect client (LED off after every attempt)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from ..protocol import CLEAR_BLACK, CLEAR_WHITE, DEFAULT_PAYLOAD_BYTES
from .bleak_transport import BleakInkTransport
from .connect import async_gatt_connect
from .errors import TransferError
from .progress import TransferProgress
from .session import EinkSession, ProgressCallback

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_CONNECT_TIMEOUT_S = 15.0

__all__ = [
    "CLEAR_BLACK",
    "CLEAR_WHITE",
    "DEFAULT_CONNECT_TIMEOUT_S",
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
        ble_device_callback: Callable[[], Any | None] | None = None,
        payload_size: int = DEFAULT_PAYLOAD_BYTES,
        connect_timeout_s: float = DEFAULT_CONNECT_TIMEOUT_S,
    ) -> None:
        self._address = address
        self._ble_device = ble_device
        self._ble_device_callback = ble_device_callback
        self._payload_size = payload_size
        self._connect_timeout_s = max(5.0, float(connect_timeout_s))

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
        client: Any | None = None
        transport: BleakInkTransport | None = None
        try:
            try:
                client = await self._async_connect()
            except TimeoutError as err:
                raise TransferError(
                    f"Timed out connecting to {self._address} "
                    f"after {self._connect_timeout_s:.0f}s"
                ) from err
            if not client.is_connected:
                raise TransferError(f"Could not connect to {self._address}")

            _LOGGER.info(
                "GATT connected to %s — opening ink characteristic",
                self._address,
            )
            transport = await BleakInkTransport.open(client)
            session = EinkSession(transport, payload_size=self._payload_size)
            return await operation(session)
        except TransferError:
            raise
        except Exception as err:  # noqa: BLE001 - map bleak/HA errors for UI
            raise TransferError(str(err) or type(err).__name__) from err
        finally:
            if transport is not None:
                await transport.close()
            if client is not None and getattr(client, "is_connected", False):
                _LOGGER.debug("Disconnecting from %s", self._address)
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("disconnect failed", exc_info=True)

    async def _async_connect(self) -> Any:
        ble_device = self._ble_device
        if self._ble_device_callback is not None:
            try:
                refreshed = self._ble_device_callback()
            except Exception:  # noqa: BLE001
                refreshed = None
            if refreshed is not None:
                ble_device = refreshed

        if ble_device is None:
            raise TransferError(
                f"No BLEDevice available to connect to {self._address}"
            )

        return await async_gatt_connect(
            ble_device,
            timeout_s=self._connect_timeout_s,
        )
