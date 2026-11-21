"""EPOS H3PRO Hybrid native USB HID protocol (0xEB 0xFE, CRC-8) & state model.

Verified against live EPOS H3PRO Hybrid (1395:0101 wired / 1395:0303 dongle)
on HID interface 3 (Usage Page 0xFFFF, Usage 0x0001, Report ID 0x01, 107B).

Frame layout (13-byte header + LE 16-bit payload words, zero-padded to 107B):
  [0]      0x01        HID Report ID
  [1..2]   0xEB 0xFE   EPOS/DSEA magic header
  [3..4]   0x0001      Protocol version (LE u16)
  [5..6]   type        0x0004 = request/reply, 0x0110 = async notification
  [7..8]   target      0x0001 = direct USB device (wired headset or dongle),
                       0x0005 = headset behind wireless dongle;
                       replies return (target - 1): 0x0000 or 0x0004
  [9..10]  length      Payload length in bytes (LE u16)
  [11..12] crc         CRC-8 (poly 0x07, init 0xFF) over payload bytes (LE u16)
  [13..]   payload     LE u16 words: (group, command, *values)

Verified hardware commands:
  0x01 / 0x09          Dongle: headset connected (0 or 1)
  0x12 / 0x03          Read battery percentage (steps of 20: 0..100)
  0x0A / 0x0B <0..255> Set sidetone level (replies with status 0)
  0x0A / 0x0C          Read sidetone level (0..255)
  0x0A / 0x11 <0|1>    Set mic noise cancellation (0=off, 1=on)
  0x0A / 0x12          Read mic noise cancellation (0 or 1)
  0x01 / 0x1F <0|1>    Set auto-sleep low-power mode (0=off, 1=on)
  0x01 / 0x20          Read auto-sleep mode (0 or 1)
  0x17 / 0x07          Async notification: physical ANC slider (0=off, 1=on)
  0x08 / 0xF0          Async notification: Bluetooth pair button (val=3)
"""

from __future__ import annotations

import json
import struct
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from eposctl.constants import (
    PID_H3PRO_DONGLE,
    PID_H3PRO_WIRED,
    REPORT_ID_CMD_01,
    REPORT_ID_CMD_05,
    REPORT_ID_CONSUMER_MEDIA,
    REPORT_ID_CONSUMER_VOLUME,
    REPORT_ID_FEAT_03,
    REPORT_ID_FEAT_04,
    REPORT_ID_TELEMETRY_01,
    TELEMETRY_FRAME_SIZE,
    VOICE_PROMPT_MODES,
)
from eposctl.transport import HidTransport, HidTransportError

# Safety guardrails: permanently block Feature reports 0x03 / 0x04 on 0xFF00
BLOCKED_FEATURE_REPORT_IDS: frozenset[int] = frozenset(
    {REPORT_ID_FEAT_03, REPORT_ID_FEAT_04}
)
SAFE_CONTROL_OUTPUT_REPORT_IDS: frozenset[int] = frozenset(
    {REPORT_ID_CMD_01, REPORT_ID_CMD_05}
)
SAFE_TELEMETRY_OUTPUT_REPORT_IDS: frozenset[int] = frozenset({REPORT_ID_TELEMETRY_01})

# Native EPOS/DSEA 0xEB 0xFE protocol constants
EPOS_VENDOR_MAGIC: bytes = b"\xEB\xFE"
EPOS_HEADER_FMT: str = "<B2sHHHHH"
EPOS_HEADER_SIZE: int = struct.calcsize(EPOS_HEADER_FMT)  # 13 bytes
EPOS_VERSION: int = 0x0001
EPOS_TYPE_REQUEST: int = 0x0004
EPOS_TYPE_NOTIFY: int = 0x0110
EPOS_TARGET_DEVICE: int = 0x0001
EPOS_TARGET_HEADSET: int = 0x0005
EPOS_STATUS_SUCCESS: int = 0x0000
SIDETONE_DEVICE_MAX: int = 0xFF

# Verified (group, command) pairs (from dciadapter.dll + live H3PRO 1395:0101 verification)
CMD_SW_VERSION_GET: tuple[int, int] = (0x01, 0x03)
CMD_CONNECTED: tuple[int, int] = (0x01, 0x09)
CMD_AUTO_SLEEP_SET: tuple[int, int] = (0x01, 0x1F)
CMD_AUTO_SLEEP_GET: tuple[int, int] = (0x01, 0x20)
CMD_AUDIO_PROMPTS_SET: tuple[int, int] = (0x07, 0x01)
CMD_AUDIO_PROMPTS_GET: tuple[int, int] = (0x07, 0x05)
CMD_SIDETONE_SET: tuple[int, int] = (0x0A, 0x0B)
CMD_SIDETONE_GET: tuple[int, int] = (0x0A, 0x0C)
CMD_MIC_NOISE_FILTER_SET: tuple[int, int] = (0x0A, 0x11)
CMD_MIC_NOISE_FILTER_GET: tuple[int, int] = (0x0A, 0x12)
CMD_BATTERY_VOLTAGE_GET: tuple[int, int] = (0x12, 0x01)
CMD_BATTERY_CHARGING_GET: tuple[int, int] = (0x12, 0x02)
CMD_BATTERY_GET: tuple[int, int] = (0x12, 0x03)
CMD_ANC_STATE_GET: tuple[int, int] = (0x17, 0x04)

# Verified AudioPromptsMode wire values on H3PRO Hybrid fw v1.3.5:
#   1 = Hardware voice prompts ON ("voice")
#   2 = Hardware voice prompts OFF ("tones" with host PipeWire chimes, or "off" silent)
AUDIO_PROMPT_MODE_TO_WIRE: dict[str, int] = {
    "voice": 1,
    "tones": 2,
    "off": 2,
}
WIRE_TO_AUDIO_PROMPT_MODE: dict[int, str] = {
    0: "off",
    1: "voice",
    2: "off",
    3: "off",
}

# Verified async notifications
EPOS_FEAT_ANC: tuple[int, int] = (0x0017, 0x0007)
EPOS_FEAT_BT_PAIR: tuple[int, int] = (0x0008, 0x00F0)


class ConnectionMode(str, Enum):
    WIRED = "wired"
    DONGLE = "dongle"
    BLUETOOTH = "bluetooth"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True)
class ConsumerEvent:
    """Decoded HID Consumer Control event from input3 (Report IDs 0x04 / 0x05)."""

    report_id: int
    events: list[str]


@dataclass(frozen=True)
class EposVendorFrame:
    """Decoded native EPOS/DSEA 0xEB 0xFE frame from input3 (Report ID 0x01)."""

    version: int
    frame_type: int
    target: int
    payload_len: int
    checksum: int
    group: int
    command: int
    values: tuple[int, ...]
    crc_valid: bool
    label: str | None = None

    # Convenience aliases for backward compatibility with sniffer/tests
    @property
    def feature_id(self) -> int:
        return self.group

    @property
    def property_id(self) -> int:
        return self.command

    @property
    def value(self) -> int:
        return self.values[0] if self.values else 0


@dataclass
class DeviceTelemetry:
    """Consolidated state of the EPOS H3PRO Hybrid headset."""

    connected: bool = False
    connection_mode: str = ConnectionMode.DISCONNECTED.value
    product_id: int | None = None
    device_name: str = "EPOS H3PRO Hybrid"
    firmware_version: str | None = None
    battery_percent: int | None = None
    battery_mv: int | None = None
    charging: bool | None = None
    anc_enabled: bool | None = None
    mic_muted: bool | None = None
    mic_noise_filter: bool | None = None
    sidetone_level: int = 0  # 0..100% (mapped to 0..255 on device)
    auto_sleep: bool | None = None
    voice_prompts: str | None = None  # "voice" (1) | "tones" (2) | "off" (0)
    eq_profile: str = "off"
    telemetry_endpoint: str | None = None
    control_endpoint: str | None = None
    last_consumer_event: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_safe_output_report(interface: str, report_id: int) -> bool:
    """Safety guardrail preventing transmission to blocked/DFU/unknown report IDs."""
    if report_id in BLOCKED_FEATURE_REPORT_IDS:
        return False
    if interface == "control":
        return report_id in SAFE_CONTROL_OUTPUT_REPORT_IDS
    if interface == "telemetry":
        return report_id in SAFE_TELEMETRY_OUTPUT_REPORT_IDS
    return False


def crc8_epos(data: bytes) -> int:
    """Compute EPOS H3PRO CRC-8 (polynomial 0x07, initial value 0xFF)."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def sidetone_percent_to_device(percent: int) -> int:
    """Map 0..100% sidetone to 0..255 hardware level."""
    clamped = max(0, min(100, percent))
    return round(clamped * SIDETONE_DEVICE_MAX / 100)


def sidetone_device_to_percent(device_level: int) -> int:
    """Map 0..255 hardware sidetone level to 0..100%."""
    clamped = max(0, min(SIDETONE_DEVICE_MAX, device_level))
    return round(clamped * 100 / SIDETONE_DEVICE_MAX)


def build_epos_request(
    group: int,
    command: int,
    values: tuple[int, ...] = (),
    target: int = EPOS_TARGET_DEVICE,
    frame_type: int = EPOS_TYPE_REQUEST,
    report_id: int = REPORT_ID_TELEMETRY_01,
) -> bytes:
    """Serialize a 107-byte native EPOS 0xEB 0xFE Output report for input3 (0xFFFF)."""
    if not is_safe_output_report("telemetry", report_id):
        raise ValueError(
            f"Safety guardrail blocked report_id=0x{report_id:02X} on telemetry interface."
        )
    words = (group & 0xFFFF, command & 0xFFFF, *(v & 0xFFFF for v in values))
    payload = struct.pack("<" + "H" * len(words), *words)
    if EPOS_HEADER_SIZE + len(payload) > TELEMETRY_FRAME_SIZE:
        raise ValueError(f"Payload too large ({len(payload)} bytes).")

    header = struct.pack(
        EPOS_HEADER_FMT,
        report_id,
        EPOS_VENDOR_MAGIC,
        EPOS_VERSION,
        frame_type,
        target,
        len(payload),
        crc8_epos(payload),
    )
    frame = (header + payload).ljust(TELEMETRY_FRAME_SIZE, b"\x00")
    assert len(frame) == TELEMETRY_FRAME_SIZE
    return frame


def decode_epos_vendor_frame(frame: bytes) -> EposVendorFrame | None:
    """Decode a native EPOS/DSEA 0xEB 0xFE HID frame from input3 (RID 0x01)."""
    if len(frame) < EPOS_HEADER_SIZE + 4 or frame[0] != REPORT_ID_TELEMETRY_01:
        return None
    if frame[1:3] != EPOS_VENDOR_MAGIC:
        return None

    _, _, version, frame_type, target, payload_len, checksum = struct.unpack_from(
        EPOS_HEADER_FMT, frame, 0
    )
    if payload_len < 4 or payload_len % 2 != 0:
        return None
    if EPOS_HEADER_SIZE + payload_len > len(frame):
        return None

    payload = frame[EPOS_HEADER_SIZE : EPOS_HEADER_SIZE + payload_len]
    crc_valid = crc8_epos(payload) == (checksum & 0xFF)
    words = struct.unpack("<" + "H" * (payload_len // 2), payload)
    group, command = words[0], words[1]
    values = words[2:]

    label: str | None = None
    if (group, command) == EPOS_FEAT_ANC:
        val = values[0] if values else 0
        label = "anc_on" if val == 1 else ("anc_off" if val == 0 else f"anc_{val}")
    elif (group, command) == EPOS_FEAT_BT_PAIR:
        label = "bt_pair"
    elif (group, command) == CMD_BATTERY_GET and values:
        label = f"battery={values[0]}%"
    elif (group, command) == CMD_SIDETONE_GET and values:
        label = f"sidetone={sidetone_device_to_percent(values[0])}%"
    elif (group, command) == CMD_MIC_NOISE_FILTER_GET and values:
        label = f"mic_noise_filter={'on' if values[0] else 'off'}"
    elif (group, command) == CMD_AUTO_SLEEP_GET and values:
        label = f"auto_sleep={'on' if values[0] else 'off'}"

    return EposVendorFrame(
        version=version,
        frame_type=frame_type,
        target=target,
        payload_len=payload_len,
        checksum=checksum,
        group=group,
        command=command,
        values=values,
        crc_valid=crc_valid,
        label=label,
    )


def decode_consumer_report(frame: bytes) -> ConsumerEvent | None:
    """Decode verified Consumer Control reports (Report ID 0x04 / 0x05) on input3."""
    if len(frame) < 2:
        return None
    rid, bits = frame[0], frame[1]

    if rid == REPORT_ID_CONSUMER_MEDIA:
        mapping = [
            (0, "play_pause"),
            (1, "pause"),
            (2, "play"),
            (3, "stop"),
            (4, "scan_next"),
            (5, "scan_prev"),
            (6, "fast_forward"),
            (7, "rewind"),
        ]
        events = [name for bit, name in mapping if bits & (1 << bit)]
        return ConsumerEvent(report_id=rid, events=events)

    if rid == REPORT_ID_CONSUMER_VOLUME:
        events: list[str] = []
        if bits & 0x01:
            events.append("volume_up")
        if bits & 0x02:
            events.append("volume_down")
        return ConsumerEvent(report_id=rid, events=events)

    return None


def parse_telemetry_frame(frame: bytes, state: DeviceTelemetry) -> DeviceTelemetry:
    """Apply an incoming HID Input frame from input3 (0xFFFF / 0x000C) to state."""
    if not frame:
        return state

    rid = frame[0]
    if rid in (REPORT_ID_CONSUMER_MEDIA, REPORT_ID_CONSUMER_VOLUME):
        ev = decode_consumer_report(frame)
        if ev and ev.events:
            state.last_consumer_event = ",".join(ev.events)
        return state

    vev = decode_epos_vendor_frame(frame)
    if vev is None:
        return state

    if (vev.group, vev.command) == EPOS_FEAT_ANC and vev.values:
        state.anc_enabled = vev.values[0] != 0
    elif (vev.group, vev.command) == EPOS_FEAT_BT_PAIR:
        state.last_consumer_event = "bt_pair"
    elif (vev.group, vev.command) == CMD_BATTERY_GET and vev.values:
        if 0 <= vev.values[0] <= 100:
            state.battery_percent = vev.values[0]
    elif (vev.group, vev.command) == CMD_SIDETONE_GET and vev.values:
        state.sidetone_level = sidetone_device_to_percent(vev.values[0])
    elif (vev.group, vev.command) == CMD_MIC_NOISE_FILTER_GET and vev.values:
        state.mic_noise_filter = vev.values[0] != 0
    elif (vev.group, vev.command) == CMD_AUTO_SLEEP_GET and vev.values:
        state.auto_sleep = vev.values[0] != 0

    return state


def build_mock_reply_frame(
    group: int,
    command: int,
    values: tuple[int, ...],
    target: int = 0x0000,
) -> bytes:
    """Build a valid native EPOS 0xEB 0xFE reply frame (used in tests & mock mode)."""
    return build_epos_request(
        group=group,
        command=command,
        values=values,
        target=target,
        frame_type=EPOS_TYPE_REQUEST,
    )


class StateCache:
    """Lightweight JSON state cache under ~/.cache/eposctl/state.json."""

    def __init__(self, path: Path | None = None, enabled: bool = True) -> None:
        self.path = path or (Path.home() / ".cache" / "eposctl" / "state.json")
        self.enabled = enabled

    def load(self) -> dict[str, Any]:
        if not self.enabled or not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self, data: dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass


class EposDevice:
    """High-level controller for the EPOS H3PRO Hybrid using native 0xEB 0xFE HID frames."""

    def __init__(
        self,
        transport: HidTransport,
        cache: StateCache | None = None,
    ) -> None:
        self.transport = transport
        self.cache = cache or StateCache()

    def _is_dongle(self) -> bool:
        ep = self.transport.endpoints()
        return ep is not None and ep.product_id == PID_H3PRO_DONGLE

    def _headset_target(self) -> int:
        return EPOS_TARGET_HEADSET if self._is_dongle() else EPOS_TARGET_DEVICE

    def _base_telemetry(self) -> DeviceTelemetry:
        cached = self.cache.load()
        ep = self.transport.endpoints()

        mode = ConnectionMode.DISCONNECTED.value
        pid = None
        name = "EPOS H3PRO Hybrid"
        tel_path = None
        ctrl_path = None
        connected = ep is not None

        if ep is not None:
            pid = ep.product_id
            name = ep.product_name
            tel_path = ep.telemetry.dev_path if ep.telemetry else None
            ctrl_path = ep.control.dev_path if ep.control else None
            if pid == PID_H3PRO_WIRED:
                mode = ConnectionMode.WIRED.value
            elif pid == PID_H3PRO_DONGLE:
                mode = ConnectionMode.DONGLE.value

        return DeviceTelemetry(
            connected=connected,
            connection_mode=mode,
            product_id=pid,
            device_name=name,
            firmware_version=cached.get("firmware_version"),
            battery_percent=cached.get("battery_percent"),
            battery_mv=cached.get("battery_mv"),
            charging=cached.get("charging"),
            anc_enabled=cached.get("anc_enabled"),
            mic_muted=cached.get("mic_muted"),
            mic_noise_filter=cached.get("mic_noise_filter"),
            sidetone_level=int(cached.get("sidetone_level", 0)),
            auto_sleep=cached.get("auto_sleep"),
            voice_prompts=cached.get("voice_prompts"),
            eq_profile=str(cached.get("eq_profile", "off")),
            telemetry_endpoint=tel_path,
            control_endpoint=ctrl_path,
        )

    def _persist(self, state: DeviceTelemetry) -> None:
        self.cache.save(
            {
                "firmware_version": state.firmware_version,
                "battery_percent": state.battery_percent,
                "battery_mv": state.battery_mv,
                "charging": state.charging,
                "anc_enabled": state.anc_enabled,
                "mic_muted": state.mic_muted,
                "mic_noise_filter": state.mic_noise_filter,
                "sidetone_level": state.sidetone_level,
                "auto_sleep": state.auto_sleep,
                "voice_prompts": state.voice_prompts,
                "eq_profile": state.eq_profile,
            }
        )

    def _send_request(
        self,
        command: tuple[int, int],
        values: tuple[int, ...] = (),
        target: int | None = None,
        timeout_ms: int = 400,
        state: DeviceTelemetry | None = None,
    ) -> tuple[int, ...] | None:
        """Send a native 0xEB 0xFE request on input3 and wait for its matching reply."""
        tgt = self._headset_target() if target is None else target
        req = build_epos_request(command[0], command[1], values=values, target=tgt)
        self.transport.write_telemetry(req)

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while True:
            rem_ms = int((deadline - time.monotonic()) * 1000)
            if rem_ms <= 0:
                return None
            rx = self.transport.read_telemetry(timeout_ms=min(rem_ms, 80))
            if not rx:
                continue
            if state is not None:
                parse_telemetry_frame(rx, state)
            vev = decode_epos_vendor_frame(rx)
            if vev is None or (vev.group, vev.command) != command:
                continue
            if tgt == EPOS_TARGET_HEADSET and vev.target == EPOS_TARGET_DEVICE:
                raise HidTransportError("Headset is switched off or out of range of dongle.")
            if vev.target == tgt - 1:
                return vev.values

    def poll_events(self, state: DeviceTelemetry, poll_timeout_ms: int = 10) -> DeviceTelemetry:
        """Non-blocking drain of async HID notifications (ANC slider, volume, BT button)."""
        if not self.transport.is_open():
            return state
        changed = False
        for _ in range(8):
            frame = self.transport.read_telemetry(timeout_ms=poll_timeout_ms)
            if frame is None:
                break
            parse_telemetry_frame(frame, state)
            changed = True
            poll_timeout_ms = 2
        if changed:
            # Preserve user-chosen prompt/EQ settings written by other eposctl processes
            latest = self.cache.load()
            if latest.get("voice_prompts"):
                state.voice_prompts = str(latest["voice_prompts"])
            if latest.get("eq_profile"):
                state.eq_profile = str(latest["eq_profile"])
            self._persist(state)
        return state

    def read_status(self, poll_timeout_ms: int = 250, query_hardware: bool = True) -> DeviceTelemetry:
        """Query live hardware telemetry (battery, sidetone, mic filter, auto-sleep) + drain events."""
        state = self._base_telemetry()
        if not self.transport.is_open():
            return state

        self.poll_events(state, poll_timeout_ms=10)

        if query_hardware:
            if self._is_dongle():
                conn_vals = self._send_request(
                    CMD_CONNECTED, target=EPOS_TARGET_DEVICE, timeout_ms=poll_timeout_ms, state=state
                )
                if conn_vals is not None and conn_vals[0] == 0:
                    state.connected = False
                    self._persist(state)
                    return state

            batt = self._send_request(CMD_BATTERY_GET, timeout_ms=poll_timeout_ms, state=state)
            if batt and 0 <= batt[0] <= 100:
                state.battery_percent = batt[0]
                if state.connection_mode == ConnectionMode.WIRED.value:
                    state.charging = True

            volt = self._send_request(CMD_BATTERY_VOLTAGE_GET, timeout_ms=poll_timeout_ms, state=state)
            if volt:
                state.battery_mv = volt[0]

            anc = self._send_request(CMD_ANC_STATE_GET, timeout_ms=poll_timeout_ms, state=state)
            if anc:
                state.anc_enabled = anc[0] != 0

            vp = self._send_request(CMD_AUDIO_PROMPTS_GET, timeout_ms=poll_timeout_ms, state=state)
            if vp:
                if vp[0] == 1:
                    state.voice_prompts = "voice"
                elif state.voice_prompts != "tones":
                    state.voice_prompts = "off"

            st = self._send_request(CMD_SIDETONE_GET, timeout_ms=poll_timeout_ms, state=state)
            if st:
                state.sidetone_level = sidetone_device_to_percent(st[0])

            nf = self._send_request(CMD_MIC_NOISE_FILTER_GET, timeout_ms=poll_timeout_ms, state=state)
            if nf:
                state.mic_noise_filter = nf[0] != 0

            slp = self._send_request(CMD_AUTO_SLEEP_GET, timeout_ms=poll_timeout_ms, state=state)
            if slp:
                state.auto_sleep = slp[0] != 0

            fw = self._send_request(CMD_SW_VERSION_GET, timeout_ms=poll_timeout_ms, state=state)
            if fw and len(fw) >= 3:
                state.firmware_version = f"{fw[0]}.{fw[1]}.{fw[2]}"

        self._persist(state)
        return state

    def set_sidetone(self, level: int) -> bytes:
        """Set hardware sidetone gain (0 = off, 1..100%) via verified 0x0A/0x0B command."""
        if not 0 <= level <= 100:
            raise ValueError("Sidetone level must be between 0 and 100.")
        dev_val = sidetone_percent_to_device(level)
        req = build_epos_request(
            CMD_SIDETONE_SET[0], CMD_SIDETONE_SET[1], values=(dev_val,), target=self._headset_target()
        )
        reply = self._send_request(CMD_SIDETONE_SET, values=(dev_val,))
        if reply is not None and reply and reply[0] != EPOS_STATUS_SUCCESS:
            raise HidTransportError(f"Headset rejected sidetone command (status={reply[0]}).")
        state = self._base_telemetry()
        state.sidetone_level = level
        self._persist(state)
        return req

    def set_mic_noise_filter(self, enabled: bool) -> bytes:
        """Toggle hardware mic noise cancellation (0x0A/0x11)."""
        val = 1 if enabled else 0
        req = build_epos_request(
            CMD_MIC_NOISE_FILTER_SET[0],
            CMD_MIC_NOISE_FILTER_SET[1],
            values=(val,),
            target=self._headset_target(),
        )
        reply = self._send_request(CMD_MIC_NOISE_FILTER_SET, values=(val,))
        if reply is not None and reply and reply[0] != EPOS_STATUS_SUCCESS:
            raise HidTransportError(f"Headset rejected mic noise filter command (status={reply[0]}).")
        state = self._base_telemetry()
        state.mic_noise_filter = enabled
        self._persist(state)
        return req

    def set_auto_sleep(self, enabled: bool) -> bytes:
        """Toggle hardware auto-sleep low-power mode (0x01/0x1F)."""
        val = 1 if enabled else 0
        req = build_epos_request(
            CMD_AUTO_SLEEP_SET[0],
            CMD_AUTO_SLEEP_SET[1],
            values=(val,),
            target=self._headset_target(),
        )
        reply = self._send_request(CMD_AUTO_SLEEP_SET, values=(val,))
        if reply is not None and reply and reply[0] != EPOS_STATUS_SUCCESS:
            raise HidTransportError(f"Headset rejected auto-sleep command (status={reply[0]}).")
        state = self._base_telemetry()
        state.auto_sleep = enabled
        self._persist(state)
        return req

    def set_voice_prompts(self, mode: str) -> bytes:
        """Set prompt preset: 'voice' (hw 1), 'tones' (hw 2 + PipeWire SFX), or 'off' (hw 2)."""
        normalized = mode.strip().lower()
        if normalized == "on":
            normalized = "voice"
        if normalized not in VOICE_PROMPT_MODES:
            raise ValueError(
                f"Invalid voice prompt mode '{mode}'. Allowed: {', '.join(VOICE_PROMPT_MODES)}."
            )
        wire_val = AUDIO_PROMPT_MODE_TO_WIRE[normalized]
        req = build_epos_request(
            CMD_AUDIO_PROMPTS_SET[0],
            CMD_AUDIO_PROMPTS_SET[1],
            values=(wire_val,),
            target=self._headset_target(),
        )
        reply = self._send_request(CMD_AUDIO_PROMPTS_SET, values=(wire_val,))
        if reply is not None and reply and reply[0] != EPOS_STATUS_SUCCESS:
            raise HidTransportError(f"Headset rejected audio prompts command (status={reply[0]}).")
        state = self._base_telemetry()
        state.voice_prompts = normalized
        self._persist(state)
        return req
