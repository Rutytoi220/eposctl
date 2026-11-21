"""Hardware and USB HID constants for the EPOS H3PRO Hybrid."""

from __future__ import annotations

# USB Vendor & Product IDs (DSEA A/S / EPOS)
VENDOR_ID: int = 0x1395

PID_H3PRO_WIRED: int = 0x0101
PID_H3PRO_DONGLE: int = 0x0303

SUPPORTED_PIDS: dict[int, str] = {
    PID_H3PRO_WIRED: "EPOS H3PRO Hybrid (Wired USB)",
    PID_H3PRO_DONGLE: "EPOS H3PRO Hybrid (Wireless Dongle GSA 70)",
}

# Vendor-defined HID Usage Pages (verified from live /sys/class/hidraw report descriptors)
USAGE_PAGE_TELEMETRY: int = 0xFFFF  # input3: Vendor telemetry & bidirectional 106B reports + Consumer Control (0x000C)
USAGE_PAGE_CONSUMER: int = 0x000C   # input3 secondary collection: Media / Volume keys
USAGE_PAGE_CONTROL: int = 0xFF00    # input4: Vendor command/datalink bridge (65B Output/Input, 13B Input, 3B Feature)

# Expected USB interface suffixes in HID_PHYS (fallback matching)
INTERFACE_TELEMETRY: str = "input3"
INTERFACE_CONTROL: str = "input4"

# input3 (Usage Page 0xFFFF) Report IDs & payload sizes (verified from descriptor)
REPORT_ID_TELEMETRY_01: int = 0x01
TELEMETRY_PAYLOAD_SIZE: int = 106  # 0x6A bytes (excluding Report ID)
TELEMETRY_FRAME_SIZE: int = 1 + TELEMETRY_PAYLOAD_SIZE  # 107 bytes
REPORT_ID_CONSUMER_MEDIA: int = 0x04  # 1B payload (Play/Pause/Next/Prev/Stop)
REPORT_ID_CONSUMER_VOLUME: int = 0x05  # 1B payload (Vol+/Vol- in bits 0-1)

# input4 (Usage Page 0xFF00) Report IDs & payload sizes (verified from descriptor)
REPORT_ID_CMD_01: int = 0x01  # 65B Output
REPORT_ID_CMD_05: int = 0x05  # 65B Output
REPORT_ID_RSP_02: int = 0x02  # 65B Input
REPORT_ID_RSP_06: int = 0x06  # 13B Input
REPORT_ID_FEAT_03: int = 0x03  # 3B Feature (WARNING: do not fuzz)
REPORT_ID_FEAT_04: int = 0x04  # 3B Feature (WARNING: do not fuzz)
CMD_PAYLOAD_SIZE: int = 65  # 0x0041 bytes (excluding Report ID)
CMD_FRAME_SIZE: int = 1 + CMD_PAYLOAD_SIZE  # 66 bytes total including Report ID

# Auto-sleep timer options (minutes; 0 = off)
SLEEP_TIMERS_MIN: tuple[int, ...] = (0, 5, 15, 30, 60)

# Audio prompt modes:
#   "voice" (wire 1) -> Hardware spoken voice prompts
#   "tones" (wire 2 + PipeWire chimes) -> Hardware voice OFF + host "Tu-DU"/"Tu-di" SFX
#   "off"   (wire 2) -> Completely silent (no voice, no tones)
VOICE_PROMPT_MODES: tuple[str, ...] = ("voice", "tones", "off")

# PipeWire EQ profiles
EQ_PROFILES: tuple[str, ...] = ("flat", "esports", "music", "movie")
EPOS_PIPEWIRE_TARGET_NODE: str = (
    "alsa_output.usb-1395_EPOS_H3PRO_0123456789ABCDEF-00.iec958-stereo"
)
EPOS_PIPEWIRE_NODE_GLOB: str = "alsa_output.usb-1395_EPOS_H3PRO*"
