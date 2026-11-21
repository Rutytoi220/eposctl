# `epos-linux` (`eposctl`)

Open-source Linux userspace driver, CLI, Waybar telemetry provider, keyboard-driven TUI, and native PipeWire `filter-chain` DSP manager for the **EPOS H3PRO Hybrid** (`VID: 0x1395`, Wired `PID: 0x0101`, Wireless Dongle GSA 70 `PID: 0x0303`).

---

## Architecture

Split cleanly into two Unix-native layers:

1. **Hardware Control Layer (`eposctl` in Python):**
   - Dynamically discovers EPOS `/dev/hidraw*` endpoints from sysfs by VID/PID and parsed HID Usage Page (`0xFFFF` for `input3` telemetry/consumer reports, `0xFF00` for `input4` command/datalink reports) — never hardcodes `/dev/hidrawN`.
   - Manages sidetone gain, battery/charging/ANC/mic telemetry, auto-sleep timer, and voice prompts with strict report-ID safety guardrails.
2. **Host Audio DSP Layer (Native PipeWire `filter-chain`):**
   - Uses `libpipewire-module-filter-chain` 5-band biquad parametric EQ profiles (`flat`, `esports`, `music`, `movie`) targeting the EPOS H3PRO ALSA output node (`alsa_output.usb-1395_EPOS_H3PRO_0123456789ABCDEF-00.iec958-stereo`).

---

## Installation

### 1. Install `udev` Rules (Non-Root `hidraw` Access)

```bash
sudo cp udev/70-epos-h3pro.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
# Prefix < 73 is required on systemd so 73-seat-late.rules applies TAG+="uaccess".
```

Verify permissions:

```bash
ls -l /dev/hidraw*
```

### 2. Install `eposctl`

Using [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev
uv run eposctl --help
```

Or install globally as an editable CLI tool:

```bash
uv tool install --editable .
```

### 3. PipeWire EQ Profiles (Optional Pre-Load)

`eposctl eq <profile>` can spawn and manage the selected `pipewire -c pipewire/epos-eq-<profile>.conf` filter-chain automatically, **or** you can pre-load all four virtual sinks into PipeWire:

```bash
mkdir -p ~/.config/pipewire/pipewire.conf.d
cp pipewire/epos-eq-*.conf ~/.config/pipewire/pipewire.conf.d/
systemctl --user restart pipewire
```

---

## Usage

### CLI

```bash
# Show human-readable telemetry & endpoints
eposctl status

# Output Waybar-compatible JSON
eposctl status --json

# Hardware controls (add --mock to test without hardware access)
eposctl sidetone 40
eposctl sidetone off
eposctl sleep 15          # off | 5 | 15 | 30 | 60
eposctl voice-prompts off # on | off

# PipeWire filter-chain EQ switcher
eposctl eq esports        # flat | esports | music | movie | off

# Interactive Textual TUI
eposctl tui
```

### Waybar Module Example

Add to `~/.config/waybar/config.jsonc`:

```jsonc
"custom/epos": {
    "exec": "eposctl status --json",
    "return-type": "json",
    "interval": 5,
    "format": "{}",
    "on-click": "eposctl eq esports",
    "on-click-right": "eposctl eq off"
}
```

---

## Protocol Reconnaissance & Reverse-Engineering Tools

- `scripts/dump_descriptors.py` — Reads full binary HID report descriptors from `/sys/class/hidraw` (no root required) and writes [`docs/HID_DESCRIPTORS.md`](docs/HID_DESCRIPTORS.md).
- `scripts/sniff_events.py` — Non-blocking passive sniffer logging timestamped hex + byte-diff frames and decoded Consumer Control events (`input3` `0x04`/`0x05`).
- `scripts/probe_protocol.py` — Safe, dry-run-by-default protocol query helper with guardrails blocking Feature reports `0x03`/`0x04`.
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) — Verified HID interface & report layout reference.
- [`docs/USBMON_CAPTURE.md`](docs/USBMON_CAPTURE.md) — Guide for capturing Windows VM / EPOS Gaming Suite HID frames with `usbmon` + Wireshark.

---

## Running Tests

```bash
uv run pytest -v
```
