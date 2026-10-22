# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Preview in the sidebar is approximate; quantization runs on upload

[0.1.2]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.2
[0.1.1]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.1
[0.1.0]: https://github.com/MatixYo/ha-eink-esl/releases/tag/v0.1.0

