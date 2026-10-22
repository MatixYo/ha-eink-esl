# E-Ink ESL for Home Assistant

Home Assistant custom integration for **electronic shelf labels (ESL)** with e-ink displays, starting with BLE devices that speak the Leeka-compatible image transfer protocol.

| | |
|---|---|
| **Domain** | `eink_esl` |
| **HACS** | Custom repository → **Integration** |
| **Version** | 0.1.3 |
| **Transport** | Bluetooth Low Energy via Home Assistant Bluetooth |

## Features

- One config entry per label (multi-device)
- Connect → transfer image → **disconnect** (tag LED turns off)
- Service: `eink_esl.upload_image`
- Sidebar panel **E-Ink ESL** (preview, send)
- Bluetooth discovery + manual address; panel model in options

## Installation (HACS)

1. HACS → **⋯ → Custom repositories** → add this GitHub repo as category **Integration**.
2. Download **E-Ink ESL**, then **restart Home Assistant**.
3. Settings → Devices & services → **Add integration** → **E-Ink ESL**.
4. Pick a discovered tag (or enter the MAC), then choose the panel model (default `bwry-350`).
5. Change the panel later via the integration **Configure** options.

Wake the label so it advertises if it does not appear in discovery. Buttonless tags sleep between ads; upload waits up to **30 seconds** for the next advertisement before connecting.

### Sidebar panel

Open **E-Ink ESL** in the HA sidebar: choose a label, drop an image, **Send**.

### Service

From automations or Developer Tools (target the ESL **device**):

| Service | Fields |
|---------|--------|
| `eink_esl.upload_image` | `image`: base64 / data URL, or a path under `/config`; optional `fit`, `mode` |

## Requirements

- Home Assistant **2024.8+** with a Bluetooth adapter or ESPHome Bluetooth proxy
- Pillow (installed automatically from the integration manifest)

## Development

```
custom_components/eink_esl/
  protocol/   # packets, packing, panel catalog (stdlib only)
  image/      # resize, quantize, dither (Pillow)
  ble/        # GATT transfer, ACK/retry, disconnect
  www/        # sidebar panel
```

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

See `.cursor/rules/` for architecture and coding standards. Protocol details: [docs/ble_transfer_protocol_en.md](docs/ble_transfer_protocol_en.md).

## Releasing (maintainers)

1. Bump `version` in `custom_components/eink_esl/manifest.json` and `pyproject.toml`.
2. Update [CHANGELOG.md](CHANGELOG.md).
3. Commit, push `main`, then create a GitHub release tagged `vX.Y.Z` (HACS picks up the tag).

## License

MIT
