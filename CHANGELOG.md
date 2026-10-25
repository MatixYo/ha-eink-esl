# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.33] - 2026-10-25

### Fixed

- Weather quantize uses nearest after 2× downscale (Floyd–Steinberg bled red precip into the temp line)

## [0.1.32] - 2026-10-25

### Changed

- Weather layout is a readable mini-meteorogram: current (temp, dew, wind arrow) + hourly spark (temp/precip/wind) + Today + 2–3 days
- Softer edges via 2× LANCZOS render before pigment mapping

## [0.1.31] - 2026-10-22

### Changed

- Last frame per label is stored in **Home Assistant Store** (`.storage/eink_esl.slots`), not browser localStorage — shared across clients
- Successful BLE upload and weather generate both write the slot; sidebar restores via `GET /api/eink_esl/slot`

## [0.1.30] - 2026-10-22

### Added

- Weather layout (current + 5-day strip) in exact B/W/Y/R pigments
- Sidebar **Generate weather** → fills Preview; **Send** uploads like an image
- Service `eink_esl.upload_weather` and `POST /api/eink_esl/weather`
- Sidebar remembers the last frame per label (weather or image) so Preview restores on reopen

## [0.1.29] - 2026-10-22

### Removed

- Temporary **Probe BLE** panel button and `eink_esl.probe_connect` service
- Direct BlueZ / `get_device` connect bypass (host-adapter-only; broke the intended ESPHome proxy path)

### Changed

- GATT connect uses Home Assistant’s Bleak wrapper only (local adapter or Bluetooth proxy)
- Sidebar shows the selected panel resolution under the label select (sizes differ by model)

## [0.1.25] - 2026-10-22

### Fixed

- Direct BlueZ fallback passes required bleak ``bluez=`` kwargs (`BleakClientBlueZDBus.__init__`)

## [0.1.24] - 2026-10-22

### Fixed

- On HA “connection slot / no scanner currently has it” (ads in history, empty live set), fall back to a **direct BlueZ backend** connect using the advertisement `BLEDevice` instead of failing before the radio is used
- Allow a connectable-history device ≤3 s old when the current scanner set is empty

## [0.1.23] - 2026-10-22

### Changed

- Safer BLE budgets so failed GATT does not wedge HA Core: upload wait ≤60 s / 2 connect attempts, Probe ≤2 attempts / ~35 s, hard `asyncio.wait_for` around every `BleakClient.connect`

## [0.1.22] - 2026-10-22

### Fixed

- GATT connect / Probe only use **connectable** advertisements (battery `0x181A` ads are often non-connectable and left HA with “connection slot / no scanner currently has it” while last ad was 2 s ago)
- Probe retries across fresh connectable ads for ~90 s instead of failing on the first attempt

## [0.1.21] - 2026-10-22

### Added

- Temporary **Probe BLE** panel button / `eink_esl.probe_connect` service: GATT connect only (same settle as LKESL), hold ~5 s for the red LED, report advertised name + whether the ink GATT service is present — to check wrong-device / host radio path without an image transfer

## [0.1.20] - 2026-10-22

### Changed

- A new **Send** aborts any in-flight upload on that label (panel button stays clickable as “Abort & send…”)
- Advertisement waits use short slices so cancel reacts within ~3 s instead of blocking up to 20 s

## [0.1.19] - 2026-10-22

### Fixed

- GATT connect uses a **single** `BleakClient.connect` on a BlueZ-bus device (`get_device`) instead of `establish_connection`’s missing-device loop (up to 9×~4 s) that burned the ad window while HA still saw advertisements
- Config entries without `unique_id` no longer reappear under **Add device**; migrate address → unique_id on setup

## [0.1.18] - 2026-10-22

### Fixed

- Connect only from a **currently scanned** / just-received advertisement — never from `last_service_info` history (that produced `no scanner currently has it` while battery ads still updated)
- Drop pre-connect sleeps (`CONNECT_DELAY` / stop-discovery settle) and skip `close_stale` before the first attempt so the live ad window is not burned
- Pass `ble_device_callback` into `establish_connection` to refresh the path mid-retry

## [0.1.17] - 2026-10-22

### Added

- Diagnostic **Battery** sensor (`sensor.*_battery`) from `0x181A` advertisement service data (same field the LKESL app shows as `power`)

### Fixed

- BLE connect no longer wraps `establish_connection` in a short `wait_for` that cancelled under bleak’s ~20 s timeout and left BlueZ in `org.bluez.Error.InProgress`
- Treat BlueZ `InProgress` as retryable; settle + wait for a fresh advertisement between attempts
- Keep the live advertisement `BLEDevice` instead of swapping to a stale `last_service_info` path (`no scanner currently has it` despite last ad a few seconds ago)
- Avoid blocking `manifest.json` read on the event loop; fix deprecated `DeviceEntry.config_entries` access

## [0.1.16] - 2026-10-22

### Fixed

- After GATT connect, wait **1 s** then refresh services before ink notify (same as LKESL `checkInkScreenDevice`) — was opening characteristics immediately with a possibly stale bleak service cache, so transfers never reached the display

## [0.1.15] - 2026-10-22

### Changed

- BLE connect mirrors the LKESL manufacturer app: 300 ms RSSI pick window, stop-settle 200 ms, **15 s × 3** GATT attempts with 500 ms gaps, then wait for the next advertisement (up to 5 min total)

## [0.1.14] - 2026-10-22

### Changed

- BLE wait-for-advertisement / connect-retry budget increased to **5 minutes** (scheduled weather updates can wait for a sleepy tag); per-attempt GATT connect stays ~20s

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

[0.1.16]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.16
[0.1.15]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.15
[0.1.14]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.14
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


