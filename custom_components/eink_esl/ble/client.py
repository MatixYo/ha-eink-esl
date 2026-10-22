"""Connect → transfer → disconnect client (LED off after every attempt)."""

from __future__ import annotations

import asyncio
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

# bleak-retry-connector uses BLEAK_TIMEOUT=20s per attempt. Outer cancels that
# are shorter leave BlueZ in org.bluez.Error.InProgress on the next try.
DEFAULT_CONNECT_TIMEOUT_S = 25.0
DEFAULT_ESTABLISH_ATTEMPTS = 1
# After a failed/cancelled connect, give BlueZ time to drop InProgress.
_POST_FAIL_BLUEZ_SETTLE_S = 1.5

# Re-export for callers that only import client.
__all__ = [
    "CLEAR_BLACK",
    "CLEAR_WHITE",
    "DEFAULT_CONNECT_TIMEOUT_S",
    "DEFAULT_ESTABLISH_ATTEMPTS",
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
        establish_attempts: int = DEFAULT_ESTABLISH_ATTEMPTS,
        close_stale_before_connect: bool = True,
    ) -> None:
        self._address = address
        self._ble_device = ble_device
        self._ble_device_callback = ble_device_callback
        self._payload_size = payload_size
        self._connect_timeout_s = max(5.0, float(connect_timeout_s))
        self._establish_attempts = max(1, int(establish_attempts))
        self._close_stale_before_connect = close_stale_before_connect

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
                # Do not wrap establish_connection in a short wait_for: cancelling
                # mid-BlueZ-connect leaves the adapter InProgress for later attempts.
                client = await self._async_connect()
            except TimeoutError as err:
                await self._async_close_stale(settle=True)
                raise TransferError(
                    f"Timed out connecting to {self._address} "
                    f"after {self._connect_timeout_s:.0f}s"
                ) from err
            except Exception:
                await self._async_close_stale(settle=True)
                raise
            if not client.is_connected:
                raise TransferError(f"Could not connect to {self._address}")

            _LOGGER.info("GATT connected to %s — opening ink characteristic", self._address)
            transport = await BleakInkTransport.open(client)
            session = EinkSession(transport, payload_size=self._payload_size)
            return await operation(session)
        except TransferError:
            raise
        except Exception as err:  # noqa: BLE001 - map bleak/HA errors for UI
            raise TransferError(str(err) or type(err).__name__) from err
        finally:
            # Disconnect even on failure so the shelf-label LED turns off.
            if transport is not None:
                await transport.close()
            if client is not None and getattr(client, "is_connected", False):
                _LOGGER.debug("Disconnecting from %s", self._address)
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("disconnect failed", exc_info=True)

    async def _async_close_stale(self, *, settle: bool = False) -> None:
        try:
            from bleak_retry_connector import close_stale_connections_by_address

            await asyncio.wait_for(
                close_stale_connections_by_address(self._address),
                timeout=3.0,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "close_stale failed for %s",
                self._address,
                exc_info=True,
            )
        if settle:
            await asyncio.sleep(_POST_FAIL_BLUEZ_SETTLE_S)

    async def _async_connect(self) -> Any:
        """Open GATT via bleak-retry-connector when HA gave us a BLEDevice."""
        if self._ble_device is not None:
            try:
                from bleak_retry_connector import (
                    BleakClientWithServiceCache,
                    close_stale_connections_by_address,
                    establish_connection,
                )
            except ImportError:
                from bleak import BleakClient

                _LOGGER.debug(
                    "bleak_retry_connector unavailable; raw BleakClient for %s",
                    self._address,
                )
                client = BleakClient(self._ble_device)
                await client.connect()
                return client

            if self._close_stale_before_connect:
                try:
                    await asyncio.wait_for(
                        close_stale_connections_by_address(self._address),
                        timeout=3.0,
                    )
                except Exception:  # noqa: BLE001
                    _LOGGER.debug(
                        "close_stale_connections_by_address failed for %s",
                        self._address,
                        exc_info=True,
                    )

            _LOGGER.info(
                "Connecting to %s (timeout=%.0fs)",
                self._address,
                self._connect_timeout_s,
            )
            # Fresh service discovery every transfer — stale bleak cache can miss
            # the ink service on sleepy ESL tags (manufacturer app always rediscovers).
            kwargs: dict[str, Any] = {
                "max_attempts": self._establish_attempts,
                "use_services_cache": False,
            }
            if self._ble_device_callback is not None:
                kwargs["ble_device_callback"] = self._ble_device_callback
            return await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                f"ESL {self._address}",
                **kwargs,
            )

        try:
            from bleak import BleakClient
        except ImportError as err:
            raise TransferError(
                "bleak is required for Bluetooth transfers"
            ) from err

        _LOGGER.debug("Connecting to %s by address string", self._address)
        client = BleakClient(self._address)
        await client.connect()
        return client
