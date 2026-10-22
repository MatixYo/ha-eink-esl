# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.13] - 2026-10-22

### Fixed

- GATT connect no longer hangs forever on "Connecting…" — hard timeout (~20s), `establish_connection` limited to 2 attempts, then retry on next advertisement

## [0.1.12] - 2026-10-22

### Fixed

- BLE connect uses the `BLEDevice` from the advertisement callback immediately (ESL tags leave the scanner's current set within ~1s, so re-querying after wait always timed out despite "last advertisement 5s ago")
- Accept any advertisement for the address while waiting; extend connect wait to 45s; use fresh `last_service_info` when age ≤ 8s

## [0.1.11] - 2026-10-22

### Fixed

- BLE connect waits for a *live* scanner advertisement (not history-only `BLEDevice`), which caused `No backend with an available connection slot … no scanner currently has it`
- Connect uses `bleak_retry_connector.establish_connection` + closes stale BlueZ links; retries slot / path failures within 30s

## [0.1.10] - 2026-10-22

### Fixed

- Preview no longer restarts on every Home Assistant state update (endless Encoding… / loader)
- Preview dedupe: reverting mode/fit while a request is in flight restores the prior canvas instead of painting the wrong result
- Preview HTTP requests are abortable via `fetchWithAuth` + `AbortSignal`
- Panel disconnect clears preview timer and in-flight abort

### Changed

- Python OKLab / Floyd–Steinberg uses a linear LUT and `array("d")` buffers (same algorithm, less overhead)

## [0.1.9] - 2026-10-22

### Changed

- Panel Send uploads the same panel-sized PNG as preview (no multi‑MB originals over the wire)
- Image base64 decode runs in a worker thread; encode timing logged

## [0.1.8] - 2026-10-22

### Fixed

- Blank E-Ink ESL panel: CSS comment used backticks inside a JS template literal and crashed `_renderShell`

## [0.1.7] - 2026-10-22

### Changed

- Preview fits locally to panel size then quantizes over HTTP (was slow sending full photos over WebSocket)
- Send disabled while encoding preview or uploading; button shows Sending…

## [0.1.6] - 2026-10-22

### Fixed

- Empty preview: hide default canvas (wrong 300×150 box), center panel-ratio placeholder and image

## [0.1.5] - 2026-10-22

### Changed

- Sidebar preview is rendered by the Python encoder over WebSocket (`eink_esl/preview`) — no duplicated quantize in JS

## [0.1.4] - 2026-10-22

### Changed

- Sidebar preview is 1:1 with encode (OKLab nearest / Floyd–Steinberg) at true panel pixel size
- Preview scales by integer CSS pixels (no stretched aspect); tighter frame without top padding
- Upload accepts `background` (`white` / `black`) so letterboxing matches the panel

## [0.1.3] - 2026-10-22

### Fixed

- Panel colors follow Home Assistant dark/light theme again
- Connect wait retries for a full 30s (ads could return immediately while Bluetooth connection slots were still busy)

## [0.1.2] - 2026-10-22

### Changed

- Sidebar panel styling closer to the standalone e-ink web tool
- Removed user-facing clear screen (service + panel buttons); send image only

## [0.1.1] - 2026-10-22

### Added

- Sidebar panel transfer status + progress bar (waits for ads, chunk upload)
- Upload wait up to 30s for the next Bluetooth advertisement

### Fixed

- Long image filenames overflowing the drop zone

## [0.1.0] - 2026-10-22

First usable HACS release.

### Added

- Leeka-compatible BLE image transfer (clear → start → chunks → display → disconnect)
- Image pipeline: resize, OKLab nearest / Floyd–Steinberg dither, 4-pixels/byte packing
- Panel catalog (BWR / BWRY sizes) with type codes for the display command
- Config flow: Bluetooth discovery (`0x181A` ads), manual MAC entry, panel picker
- Options flow to change panel model per label
- Services: `eink_esl.upload_image`, `eink_esl.clear_screen`
- Sidebar panel **E-Ink ESL** (device pick, preview, send, clear)
- Unit tests for protocol, image, discovery, BLE ACK/retry, and image input decoding

### Notes

- Tags must be in range of a Home Assistant Bluetooth adapter or proxy
- Discovery can surface other `0x181A` devices; ignore unrelated ones or use manual address entry
- Sidebar preview mirrors server quantization (from 0.1.4)

[0.1.13]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.13
[0.1.12]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.12
[0.1.11]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.11
[0.1.10]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.10
[0.1.9]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.9
[0.1.8]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.8
[0.1.7]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.7
[0.1.6]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.6
[0.1.5]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.5
[0.1.4]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.4
[0.1.3]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.3
[0.1.2]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.2
[0.1.1]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.1
[0.1.0]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.0


