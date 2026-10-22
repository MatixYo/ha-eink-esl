"""ACK/retry unit tests for ``EinkSession`` with a fake characteristic."""

from __future__ import annotations

import pytest

from custom_components.eink_esl.ble import (
    EinkSession,
    PacketMismatchError,
    TransferAborted,
    TransferError,
    TransferProgress,
)
from custom_components.eink_esl.protocol import (
    CLEAR_WHITE,
    CMD_CHUNK,
    CMD_CLEAR,
    CMD_DISPLAY,
    CMD_START,
)

from .fake_ink_transport import FakeInkTransport


@pytest.mark.asyncio
async def test_clear_sends_command_and_waits_for_status_ack() -> None:
    transport = FakeInkTransport()
    session = EinkSession(transport)
    await session.clear(CLEAR_WHITE)
    assert len(transport.writes) == 1
    assert transport.writes[0][0][0] == CMD_CLEAR


@pytest.mark.asyncio
async def test_upload_happy_path_reports_phases() -> None:
    transport = FakeInkTransport()
    session = EinkSession(transport, payload_size=4)
    image = bytes([0x55] * 10)
    phases: list[str] = []

    def on_progress(progress: TransferProgress) -> None:
        phases.append(progress.phase)

    await session.upload(image, device_type=0x0A, on_progress=on_progress)

    commands = [packet[0] for packet, _ in transport.writes]
    assert commands[0] == CMD_CLEAR
    assert commands[1] == CMD_START
    assert commands[2] == CMD_CHUNK
    assert commands[-1] == CMD_DISPLAY
    assert phases[0] == "clear"
    assert phases[1] == "start"
    assert "chunks" in phases
    assert phases[-1] == "display"
    # 10 bytes / 4 → 3 chunks
    assert commands.count(CMD_CHUNK) == 3


@pytest.mark.asyncio
async def test_retries_when_ack_is_missing_then_succeeds() -> None:
    transport = FakeInkTransport(fail_acks=1)
    session = EinkSession(transport, status_ack_timeout_s=0.05)
    await session.clear(CLEAR_WHITE)
    assert len(transport.writes) == 2


@pytest.mark.asyncio
async def test_raises_after_max_ack_retries() -> None:
    transport = FakeInkTransport(fail_acks=10)
    session = EinkSession(transport, status_ack_timeout_s=0.05)
    with pytest.raises(TransferError, match="No ACK"):
        await session.clear(CLEAR_WHITE)
    assert len(transport.writes) == 3


@pytest.mark.asyncio
async def test_packet_mismatch_restarts_transfer_once() -> None:
    transport = FakeInkTransport(mismatch_on_packet=0)
    session = EinkSession(transport, payload_size=8)
    image = bytes([0x55] * 8)
    await session.upload(image, device_type=0x08)
    # First attempt fails on chunk 0; second attempt completes.
    assert sum(1 for packet, _ in transport.writes if packet[0] == CMD_CLEAR) == 2
    assert transport.writes[-1][0][0] == CMD_DISPLAY


@pytest.mark.asyncio
async def test_second_packet_mismatch_raises() -> None:
    class AlwaysMismatch(FakeInkTransport):
        async def write(self, data: bytes, *, response: bool) -> None:
            self.writes.append((data, response))
            command = data[0]
            if command in (CMD_CLEAR, CMD_START, CMD_DISPLAY):
                await self._queue.put(bytes((0x05, 0x00)))
                return
            if command == CMD_CHUNK:
                await self._queue.put(bytes((0x05, 0x00, 0x99)))
                return
            raise AssertionError(f"Unexpected command 0x{command:02x}")

    session = EinkSession(AlwaysMismatch(), payload_size=4)
    with pytest.raises(PacketMismatchError):
        await session.upload(bytes([0x55] * 4), device_type=0x01)


@pytest.mark.asyncio
async def test_abort_stops_upload() -> None:
    transport = FakeInkTransport()
    session = EinkSession(transport, payload_size=4)
    aborted = False

    def abort() -> bool:
        return aborted

    async def run() -> None:
        nonlocal aborted
        # Abort after first progress callback by flipping during upload.
        def on_progress(progress: TransferProgress) -> None:
            nonlocal aborted
            if progress.phase == "start":
                aborted = True

        await session.upload(
            bytes([0x55] * 20),
            device_type=0x0A,
            abort=abort,
            on_progress=on_progress,
        )

    with pytest.raises(TransferAborted):
        await run()


@pytest.mark.asyncio
async def test_switches_to_write_with_response_after_no_ack() -> None:
    transport = FakeInkTransport(
        write_with_response=True,
        write_without_response=True,
        drop_until_response_write=True,
    )
    session = EinkSession(transport, status_ack_timeout_s=0.05)
    await session.clear(CLEAR_WHITE)
    assert any(response for _, response in transport.writes)
