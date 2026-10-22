"""In-memory ink transport for BLE session unit tests."""

from __future__ import annotations

import asyncio

from custom_components.eink_esl.protocol import (
    CMD_ACK,
    CMD_CHUNK,
    CMD_CLEAR,
    CMD_DISPLAY,
    CMD_START,
)


class FakeInkTransport:
    """Auto-ACKs well-formed commands; configurable failure modes for tests."""

    def __init__(
        self,
        *,
        write_with_response: bool = True,
        write_without_response: bool = True,
        fail_acks: int = 0,
        mismatch_on_packet: int | None = None,
        drop_until_response_write: bool = False,
    ) -> None:
        self.supports_write_with_response = write_with_response
        self.supports_write_without_response = write_without_response
        self._fail_acks = fail_acks
        self._mismatch_on_packet = mismatch_on_packet
        self._drop_until_response_write = drop_until_response_write
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.writes: list[tuple[bytes, bool]] = []

    def drain_notifications(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def write(self, data: bytes, *, response: bool) -> None:
        self.writes.append((data, response))
        if self._drop_until_response_write and not response:
            # Simulate devices that never ACK write-without-response.
            return
        if self._fail_acks > 0:
            self._fail_acks -= 1
            return

        command = data[0]
        if command in (CMD_CLEAR, CMD_START, CMD_DISPLAY):
            await self._queue.put(bytes((CMD_ACK, 0x00)))
            return
        if command == CMD_CHUNK:
            packet_number = (data[1] << 8) | data[2]
            if self._mismatch_on_packet == packet_number:
                self._mismatch_on_packet = None
                await self._queue.put(
                    bytes((CMD_ACK, 0x00, (packet_number + 1) & 0xFF))
                )
                return
            await self._queue.put(
                bytes(
                    (
                        CMD_ACK,
                        (packet_number >> 8) & 0xFF,
                        packet_number & 0xFF,
                    )
                )
            )
            return
        raise AssertionError(f"Unexpected command 0x{command:02x}")

    async def next_notification(self, timeout_s: float) -> bytes:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout_s)
        except TimeoutError as err:
            raise TimeoutError("No ACK") from err
