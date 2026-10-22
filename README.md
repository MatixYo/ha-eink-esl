# E-Ink ESL for Home Assistant

Home Assistant custom integration for **electronic shelf labels (ESL)** with e-ink displays, starting with BLE devices that speak the Leeka-compatible image transfer protocol.

| | |
|---|---|
| **Domain** | `eink_esl` |
| **HACS** | Custom repository → Integration |
| **Transport (MVP)** | Bluetooth Low Energy via Home Assistant Bluetooth |

## Status

Early scaffold. Not ready for daily use yet.

Planned MVP:

- Multi-device config entries (one label = one entry)
- Connect → transfer image → **disconnect** (so the tag LED turns off)
- Image upload / clear services
- Lovelace card similar to the standalone web tool

## Installation (when releasable)

1. Add this repository in HACS as a custom **Integration**.
2. Download **E-Ink ESL**, restart Home Assistant.
3. Settings → Devices & services → Add integration → **E-Ink ESL**.

## Development layout

```
custom_components/eink_esl/
  protocol/   # packet build/parse, packing (no HA deps)
  image/      # resize, quantize, dither (Pillow)
  ble/        # GATT transfer, ACK/retry, disconnect
  …           # config flow, entities, services
```

See `.cursor/rules/` for architecture and coding standards.

## Protocol

Device BLE transfer details: [docs/ble_transfer_protocol_en.md](docs/ble_transfer_protocol_en.md).

## License

MIT
