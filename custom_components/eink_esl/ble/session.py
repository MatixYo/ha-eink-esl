"""ACK/retry transfer session over an ``InkTransport`` (no Bleak/HA deps)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..protocol import (
    ACK_STATUS_OK,
    ACK_TIMEOUT_MS,
    CLEAR_WHITE,
    DEFAULT_PAYLOAD_BYTES,
    MAX_RETRIES,
    build_chunk,
    build_clear,
    build_display,
    build_start,
    read_chunk_ack,
    read_status_ack,
    split_payload,
    to_hex,
)
from .errors import PacketMismatchError, TransferAborted, TransferError
from .progress import TransferProgress
from .transport import InkTransport

_LOGGER = logging.getLogger(__name__)

# Status commands get a longer window; chunks stay at the protocol 2s ACK.
_STATUS_ACK_TIMEOUT_MS = 5000
_SMALLER_PAYLOADS = (100, 40, 17)

ProgressCallback = Callable[[TransferProgress], None]


def _is_length_error(error: BaseException) -> bool:
    message = str(error).lower()
    return "length" in message or "mtu" in message or "too long" in message


def _raise_if_aborted(abort: Callable[[], bool] | None) -> None:
    if abort is not None and abort():
        raise TransferAborted()


class EinkSession:
    """Clear / upload image using notify ACKs, matching the web app link."""

    def __init__(
        self,
        transport: InkTransport,
        *,
        payload_size: int = DEFAULT_PAYLOAD_BYTES,
        status_ack_timeout_s: float = _STATUS_ACK_TIMEOUT_MS / 1000.0,
        chunk_ack_timeout_s: float = ACK_TIMEOUT_MS / 1000.0,
    ) -> None:
        self._transport = transport
        self._payload_size = payload_size
        self._status_ack_timeout_s = status_ack_timeout_s
        self._chunk_ack_timeout_s = chunk_ack_timeout_s
        self._prefer_without_response = transport.supports_write_without_response

    @property
    def payload_size(self) -> int:
        return self._payload_size

    def set_payload_size(self, size: int) -> None:
        self._payload_size = size

    async def clear(
        self,
        color: int,
        *,
        abort: Callable[[], bool] | None = None,
    ) -> None:
        label = "Clear white" if color == CLEAR_WHITE else "Clear black"
        await self._send_status(build_clear(color), label, abort)

    async def upload(
        self,
        image: bytes,
        device_type: int,
        *,
        abort: Callable[[], bool] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        payload = self._payload_size
        restarted_for_mismatch = False

        while True:
            try:
                await self._upload_once(
                    image, device_type, payload, abort, on_progress
                )
                self._payload_size = payload
                return
            except TransferAborted:
                raise
            except PacketMismatchError:
                if restarted_for_mismatch:
                    raise
                restarted_for_mismatch = True
                _LOGGER.info("Packet number mismatch, restarting transfer")
            except TransferError as err:
                if _is_length_error(err):
                    smaller = next((size for size in _SMALLER_PAYLOADS if size < payload), None)
                    if smaller is not None:
                        payload = smaller
                        restarted_for_mismatch = False
                        _LOGGER.info("MTU too small, retrying at %s B", smaller)
                        continue
                raise
            except Exception as err:
                if _is_length_error(err):
                    smaller = next((size for size in _SMALLER_PAYLOADS if size < payload), None)
                    if smaller is not None:
                        payload = smaller
                        restarted_for_mismatch = False
                        _LOGGER.info("MTU too small, retrying at %s B", smaller)
                        continue
                raise

    async def _upload_once(
        self,
        image: bytes,
        device_type: int,
        payload: int,
        abort: Callable[[], bool] | None,
        on_progress: ProgressCallback | None,
    ) -> None:
        def report(progress: TransferProgress) -> None:
            if on_progress is not None:
                on_progress(progress)

        _raise_if_aborted(abort)
        report(TransferProgress("clear", 0, 1))
        await self._send_status(build_clear(CLEAR_WHITE), "Clear", abort)

        _raise_if_aborted(abort)
        report(TransferProgress("start", 0, 1))
        await self._send_status(
            build_start(len(image)), f"Start {len(image)} B", abort
        )

        parts = split_payload(image, payload)
        report(TransferProgress("chunks", 0, len(parts)))
        for index, part in enumerate(parts):
            _raise_if_aborted(abort)
            await self._send_chunk(build_chunk(index, part), index, abort)
            report(TransferProgress("chunks", index + 1, len(parts)))

        _raise_if_aborted(abort)
        report(TransferProgress("display", 0, 1))
        await self._send_status(
            build_display(device_type),
            f"Display 0x{device_type:02x}",
            abort,
        )

    async def _send_status(
        self,
        packet: bytes,
        label: str,
        abort: Callable[[], bool] | None,
    ) -> None:
        await self._send_with_retry(
            packet,
            label,
            abort,
            self._status_ack_timeout_s,
            self._match_status_ack,
        )

    async def _send_chunk(
        self,
        packet: bytes,
        packet_number: int,
        abort: Callable[[], bool] | None,
    ) -> None:
        def match(payload: bytes) -> str | BaseException:
            received = read_chunk_ack(payload)
            if received is None:
                return "ignore"
            if received != packet_number:
                return PacketMismatchError(received, packet_number)
            return "ok"

        await self._send_with_retry(
            packet,
            f"Packet {packet_number}",
            abort,
            self._chunk_ack_timeout_s,
            match,
        )

    @staticmethod
    def _match_status_ack(payload: bytes) -> str | BaseException:
        status = read_status_ack(payload)
        if status is None:
            return "ignore"
        if status != ACK_STATUS_OK:
            return TransferError(f"Rejected, status 0x{status:02x}")
        return "ok"

    async def _send_with_retry(
        self,
        packet: bytes,
        label: str,
        abort: Callable[[], bool] | None,
        timeout_s: float,
        match: Callable[[bytes], str | BaseException],
    ) -> None:
        last_error: BaseException | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            _raise_if_aborted(abort)
            self._transport.drain_notifications()
            try:
                _LOGGER.debug("%s #%s: %s", label, attempt, to_hex(packet, 8))
                await self._write(packet)
                # Keep reading notifies until a matching ACK or timeout.
                while True:
                    try:
                        notification = await self._transport.next_notification(
                            timeout_s
                        )
                    except TimeoutError as err:
                        raise TransferError("No ACK") from err
                    result = match(notification)
                    if result == "ignore":
                        continue
                    if isinstance(result, BaseException):
                        raise result
                    return
            except TransferAborted:
                raise
            except PacketMismatchError:
                raise
            except Exception as err:
                last_error = err
                if (
                    self._can_switch_write()
                    and isinstance(err, TransferError)
                    and str(err).startswith("No ACK")
                ):
                    self._prefer_without_response = not self._prefer_without_response
                    _LOGGER.debug(
                        "Retry %s response",
                        "without" if self._prefer_without_response else "with",
                    )
                if _is_length_error(err) or attempt == MAX_RETRIES:
                    if isinstance(err, TransferError):
                        raise
                    raise TransferError(str(err)) from err
                _LOGGER.debug("%s: %s", label, err)

        if last_error is not None:
            if isinstance(last_error, TransferError):
                raise last_error
            raise TransferError(str(last_error)) from last_error
        raise TransferError("Transfer failed")

    def _can_switch_write(self) -> bool:
        return (
            self._transport.supports_write_with_response
            and self._transport.supports_write_without_response
        )

    async def _write(self, packet: bytes) -> None:
        without = (
            self._prefer_without_response
            and self._transport.supports_write_without_response
        )
        if without:
            await self._transport.write(packet, response=False)
            return
        if self._transport.supports_write_with_response:
            await self._transport.write(packet, response=True)
            return
        if self._transport.supports_write_without_response:
            await self._transport.write(packet, response=False)
            return
        raise TransferError("Characteristic is not writable")
