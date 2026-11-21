# EPOS H3PRO Hybrid — USB HID Protocol Reference

This document records the verified USB HID interfaces, report layouts, safety guardrails, and telemetry mappings for the **EPOS H3PRO Hybrid** (`VID: 0x1395`, Wired `PID: 0x0101`, Wireless Dongle GSA 70 `PID: 0x0303`).

---

## 1. Verified HID Interfaces (Live Descriptor Dump)

See [HID_DESCRIPTORS.md](HID_DESCRIPTORS.md) for the complete raw and decoded report descriptors collected from `/sys/class/hidraw`.

| USB Interface | Primary Usage Page | Report ID | Direction | Payload Bytes | Total Frame (incl. ID) | Role / Status |
|---------------|--------------------|-----------|-----------|---------------|------------------------|---------------|
| `input3` | `0xFFFF` | `0x01` | Input | 106 | 107 | Vendor telemetry / async event channel |
| `input3` | `0xFFFF` | `0x01` | Output | 106 | 107 | Vendor query / host-to-headset channel |
| `input3` | `0x000C` | `0x04` | Input | 1 | 2 | **VERIFIED** Consumer Control media keys |
| `input3` | `0x000C` | `0x05` | Input | 1 | 2 | **VERIFIED** Consumer Control volume wheel |
| `input4` | `0xFF00` | `0x01` | Output | 65 | 66 | Vendor command / datalink Output |
| `input4` | `0xFF00` | `0x05` | Output | 65 | 66 | Vendor command / datalink Output (alt) |
| `input4` | `0xFF00` | `0x02` | Input | 65 | 66 | Vendor ACK / response Input |
| `input4` | `0xFF00` | `0x06` | Input | 13 | 14 | Vendor short status / ACK Input |
| `input4` | `0xFF00` | `0x03` | Feature | 3 | 4 | **BLOCKED** (Safety guardrail — potential DFU/NVRAM) |
| `input4` | `0xFF00` | `0x04` | Feature | 3 | 4 | **BLOCKED** (Safety guardrail — potential DFU/NVRAM) |

---

## 2. Verified Consumer Control Reports (`input3`, Usage Page `0x000C`)

### Report ID `0x04` — Media Controls (2 bytes total)

| Byte | Bit | Usage ID | Event |
|------|-----|----------|-------|
| `0` | `0..7` | — | Report ID (`0x04`) |
| `1` | `0` | `0x00CD` | Play / Pause |
| `1` | `1` | `0x00B1` | Pause |
| `1` | `2` | `0x00B0` | Play |
| `1` | `3` | `0x00B7` | Stop |
| `1` | `4` | `0x00B5` | Scan Next Track |
| `1` | `5` | `0x00B6` | Scan Previous Track |
| `1` | `6` | `0x00B3` | Fast Forward |
| `1` | `7` | `0x00B4` | Rewind |

### Report ID `0x05` — Volume Wheel (2 bytes total)

| Byte | Bit | Usage ID | Event |
|------|-----|----------|-------|
| `0` | `0..7` | — | Report ID (`0x05`) |
| `1` | `0` | `0x00E9` | Volume Increment (wheel up) |
| `1` | `1` | `0x00EA` | Volume Decrement (wheel down) |
| `1` | `2..7` | — | Constant padding (`0`) |

---

## 3. Verified Native EPOS/DSEA `0xEB 0xFE` Protocol (`input3`, Usage Page `0xFFFF`)

Both the wired headset (`1395:0101`) and wireless dongle (`1395:0303`) use **107-byte HID reports** (`Report ID 0x01` + 106-byte payload) on `input3` (`Usage Page 0xFFFF`, `Usage 0x0001`).

### Frame Layout (13-byte header + LE 16-bit payload words, zero-padded to 107B)

| Byte Offset | Field | Encoding | Description |
|-------------|-------|----------|-------------|
| `0` | `report_id` | `u8` | `0x01` |
| `1..2` | `magic` | `2B` | `0xEB 0xFE` |
| `3..4` | `version` | `u16 LE` | `0x0001` |
| `5..6` | `type` | `u16 LE` | `0x0004` = request/reply, `0x0110` = async notification |
| `7..8` | `target` | `u16 LE` | `0x0001` = wired headset / dongle, `0x0005` = headset via dongle; replies return `target - 1` (`0x0000` / `0x0004`) |
| `9..10` | `length` | `u16 LE` | Payload byte length |
| `11..12` | `crc` | `u16 LE` | **CRC-8** (polynomial `0x07`, initial value `0xFF`) over payload bytes `[13 .. 13+length]` |
| `13..` | `payload` | `u16 LE[]` | `(group, command, *values)` |

### Verified Hardware Commands (`input3`, `Report ID 0x01`)

See [DSEA_COMMANDS.md](DSEA_COMMANDS.md) for the complete 171-command table extracted statically from `dciadapter.dll` (`epos::dci::QtilSecomparserGenerated`).

| Group / Cmd | Direction | Values | Description |
|-------------|-----------|--------|-------------|
| `0x01 / 0x03` | Query | `-> [maj, min, pat]` | **Firmware version** (`1.3.5`) — **VERIFIED ON LIVE HARDWARE** |
| `0x01 / 0x09` | Query | `-> [0\|1]` | Dongle only: headset connected (`1`) or offline (`0`) |
| `0x01 / 0x1F` | Set | `[0\|1] -> [0]` | **Set auto-sleep low-power mode** (`0`=off, `1`=on) — **VERIFIED** |
| `0x01 / 0x20` | Query | `-> [0\|1]` | **Read auto-sleep mode** — **VERIFIED ON LIVE HARDWARE** |
| `0x01 / 0x22` | Query | `-> [min]` | **Read auto-power-off timer** (`30` min) — **VERIFIED ON LIVE HARDWARE** |
| `0x07 / 0x01` | Set | `[0\|1\|2] -> [0]` | **Set Audio Prompts Mode** (`1`=Voice, `2`=Tones/SFX only, `0`=Off) — **VERIFIED ON LIVE HARDWARE** |
| `0x07 / 0x03` | Query | `-> [lang]` | **Read Voice Prompt Language** (`0`=English) — **VERIFIED ON LIVE HARDWARE** |
| `0x07 / 0x05` | Query | `-> [0\|1\|2]` | **Read Audio Prompts Mode** (`1 -> 2` persisted!) — **VERIFIED ON LIVE HARDWARE** |
| `0x0A / 0x0B` | Set | `[0..255] -> [0]` | **Set sidetone** (`0..255`, replies `0` on success) — **VERIFIED** |
| `0x0A / 0x0C` | Query | `-> [0..255]` | **Read sidetone** — **VERIFIED ON LIVE HARDWARE** |
| `0x0A / 0x11` | Set | `[0\|1] -> [0]` | **Set mic noise cancellation** (`0`=off, `1`=on) — **VERIFIED** |
| `0x0A / 0x12` | Query | `-> [0\|1]` | **Read mic noise cancellation** — **VERIFIED ON LIVE HARDWARE** |
| `0x12 / 0x01` | Query | `-> [mV, lvl]` | **Battery voltage & level** (`4158 mV, level 5`) — **VERIFIED ON LIVE HARDWARE** |
| `0x12 / 0x02` | Query | `-> [status]` | **Battery charging status** (`5`) — **VERIFIED ON LIVE HARDWARE** |
| `0x12 / 0x03` | Query | `-> [0..100]` | **Live battery percentage** (steps of 20) — **VERIFIED ON LIVE HARDWARE** |
| `0x17 / 0x04` | Query | `-> [0\|1]` | **Read ANC state** (`0`=off, `1`=on) — **VERIFIED ON LIVE HARDWARE** |
| `0x17 / 0x07` | Async Notify | `[0\|1]` | **Physical ANC slider** (`0`=off, `1`=on) — **VERIFIED ON LIVE HARDWARE** |
| `0x08 / 0xF0` | Async Notify | `[3]` | **Bluetooth pair button** — **VERIFIED ON LIVE HARDWARE** |

---

## 4. Hardware Capture Log (Live `1395:0101` Observations)

Captured via `uv run python scripts/sniff_events.py --both --log captures/live.jsonl`:

| Physical Action | Interface | Report ID | Frame Header / Key Bytes | Observed Values |
|-----------------|-----------|-----------|--------------------------|-----------------|
| Volume wheel up | `input3` | `0x05` (5B) | `05 01 00 00 00` -> `05 00 00 00 00` | `[1]` bit 0 (`0x01` -> `0x00`) **VERIFIED** |
| Volume wheel down | `input3` | `0x05` (5B) | `05 02 00 00 00` -> `05 00 00 00 00` | `[1]` bit 1 (`0x02` -> `0x00`) **VERIFIED** |
| Bluetooth pair button | `input3` | `0x01` (107B) | `01 EB FE 01 00 FF 01 00 00 0E 00 80 00 08 00 F0 00 03 00` | `ch=0xFF`, `feat=0x0008`, `prop=0x00F0`, `val=0x0003` **VERIFIED** |
| ANC toggle switch ON | `input3` | `0x01` (107B) | `01 EB FE 01 00 10 01 00 00 06 00 99 00 17 00 07 00 01 00` | `ch=0x10`, `feat=0x0017`, `prop=0x0007`, `val=0x0001` **VERIFIED** |
| ANC toggle switch OFF | `input3` | `0x01` (107B) | `01 EB FE 01 00 10 01 00 00 06 00 8C 00 17 00 07 00 00 00` | `ch=0x10`, `feat=0x0017`, `prop=0x0007`, `val=0x0000` **VERIFIED** |

### Discovered Real EPOS/DSEA Vendor Packet Structure (`input3`, Report ID `0x01`, 107B)

Live captures revealed the headset's native vendor framing on `input3` (`Usage Page 0xFFFF`):

| Byte Offset | Observed Hex | Meaning (Inferred from Live Capture) |
|-------------|--------------|--------------------------------------|
| `0` | `01` | HID Report ID (`0x01`) |
| `1..2` | `EB FE` | EPOS/DSEA vendor frame magic header (`0xEB 0xFE`) |
| `3..4` | `01 00` | Protocol version / header word (`0x0001` LE) |
| `5` | `FF` / `10` | Target / channel / message class (`0xFF` broadcast / `0x10` control event) |
| `6..8` | `01 00 00` | Flags / sequence / reserved |
| `9..10` | `0E 00` / `06 00` | Payload length in bytes (16-bit LE: `14` / `6`) |
| `11..12` | `80 00` / `99 00` / `8C 00` | Checksum / CRC byte (changes `0x99 -> 0x8C` when payload bit 0 flips) |
| `13..14` | `08 00` / `17 00` | Feature / module ID (16-bit LE) |
| `15..16` | `F0 00` / `07 00` | Property / event ID (16-bit LE) |
| `17..18` | `03 00` / `01 00` / `00 00` | State / value (16-bit LE, e.g. `1` = ON, `0` = OFF) |

---

## 5. Safety Guardrails

1. **Blocked Feature Reports:** `input4` Feature Report IDs `0x03` and `0x04` (3 bytes each) are permanently blocked by `is_safe_output_report()`. On Qualcomm/CSR-based USB HID bridges (`Usage Page 0xFF00`), short 3-byte Feature reports can trigger DFU/bootloader or NVRAM configuration modes.
2. **No Blind Fuzzing:** `scripts/probe_protocol.py` defaults to `--dry-run` and refuses to transmit to any non-whitelisted report ID.
3. **No Local Windows Binaries:** No `EPOSGamingSuiteService.exe` or vendor DLLs were found on this host; exact firmware write opcodes should be confirmed using the non-invasive `usbmon` capture workflow in [USBMON_CAPTURE.md](USBMON_CAPTURE.md).
