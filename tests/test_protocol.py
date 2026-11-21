"""Unit tests for native EPOS 0xEB 0xFE CRC-8 protocol, guardrails, and EposDevice."""

from __future__ import annotations

from pathlib import Path

import pytest

from eposctl.constants import (
    REPORT_ID_CMD_01,
    REPORT_ID_CMD_05,
    REPORT_ID_FEAT_03,
    REPORT_ID_FEAT_04,
    REPORT_ID_TELEMETRY_01,
    TELEMETRY_FRAME_SIZE,
)
from eposctl.protocol import (
    CMD_AUTO_SLEEP_GET,
    CMD_AUTO_SLEEP_SET,
    CMD_BATTERY_GET,
    CMD_MIC_NOISE_FILTER_GET,
    CMD_MIC_NOISE_FILTER_SET,
    CMD_SIDETONE_GET,
    CMD_SIDETONE_SET,
    DeviceTelemetry,
    EposDevice,
    StateCache,
    build_epos_request,
    build_mock_reply_frame,
    crc8_epos,
    decode_consumer_report,
    decode_epos_vendor_frame,
    is_safe_output_report,
    parse_telemetry_frame,
    sidetone_device_to_percent,
    sidetone_percent_to_device,
)
from eposctl.transport import MockHidTransport


def test_safety_guardrails_block_feature_and_unknown_reports() -> None:
    assert is_safe_output_report("control", REPORT_ID_CMD_01) is True
    assert is_safe_output_report("control", REPORT_ID_CMD_05) is True
    assert is_safe_output_report("telemetry", REPORT_ID_TELEMETRY_01) is True

    # Permanently blocked Feature reports on 0xFF00
    assert is_safe_output_report("control", REPORT_ID_FEAT_03) is False
    assert is_safe_output_report("control", REPORT_ID_FEAT_04) is False
    assert is_safe_output_report("control", 0x99) is False
    assert is_safe_output_report("telemetry", 0x05) is False

    with pytest.raises(ValueError, match="Safety guardrail"):
        build_epos_request(0x12, 0x03, report_id=REPORT_ID_FEAT_03)


def test_crc8_matches_live_captured_frames() -> None:
    # Exact ANC ON / OFF payloads captured from live 1395:0101 hardware:
    #   ANC ON : 17 00 07 00 01 00 -> CRC 0x99
    #   ANC OFF: 17 00 07 00 00 00 -> CRC 0x8C
    assert crc8_epos(bytes.fromhex("170007000100")) == 0x99
    assert crc8_epos(bytes.fromhex("170007000000")) == 0x8C


def test_build_and_decode_epos_request() -> None:
    req = build_epos_request(*CMD_BATTERY_GET)
    assert len(req) == TELEMETRY_FRAME_SIZE
    assert req[0] == REPORT_ID_TELEMETRY_01
    assert req[1:3] == b"\xEB\xFE"

    parsed = decode_epos_vendor_frame(req)
    assert parsed is not None
    assert parsed.crc_valid is True
    assert (parsed.group, parsed.command) == CMD_BATTERY_GET


def test_decode_verified_consumer_reports() -> None:
    vol_up = decode_consumer_report(bytes([0x05, 0x01]))
    assert vol_up is not None and vol_up.events == ["volume_up"]

    vol_down = decode_consumer_report(bytes([0x05, 0x02]))
    assert vol_down is not None and vol_down.events == ["volume_down"]

    play_pause = decode_consumer_report(bytes([0x04, 0x01]))
    assert play_pause is not None and play_pause.events == ["play_pause"]

    next_prev = decode_consumer_report(bytes([0x04, 0x30]))
    assert next_prev is not None and next_prev.events == ["scan_next", "scan_prev"]


def test_decode_live_captured_epos_vendor_frames() -> None:
    bt_pair_frame = bytes.fromhex("01EBFE0100FF0100000E0080000800F0000300") + b"\x00" * 88
    anc_on_frame = bytes.fromhex("01EBFE01001001000006009900170007000100") + b"\x00" * 88
    anc_off_frame = bytes.fromhex("01EBFE01001001000006008C00170007000000") + b"\x00" * 88

    ev_bt = decode_epos_vendor_frame(bt_pair_frame)
    assert ev_bt is not None and ev_bt.label == "bt_pair"

    ev_on = decode_epos_vendor_frame(anc_on_frame)
    assert ev_on is not None and ev_on.label == "anc_on" and ev_on.crc_valid is True

    ev_off = decode_epos_vendor_frame(anc_off_frame)
    assert ev_off is not None and ev_off.label == "anc_off" and ev_off.crc_valid is True

    state = DeviceTelemetry()
    parse_telemetry_frame(anc_on_frame, state)
    assert state.anc_enabled is True
    parse_telemetry_frame(anc_off_frame, state)
    assert state.anc_enabled is False
    parse_telemetry_frame(bt_pair_frame, state)
    assert state.last_consumer_event == "bt_pair"


def test_sidetone_scaling_roundtrip() -> None:
    assert sidetone_percent_to_device(0) == 0
    assert sidetone_percent_to_device(100) == 255
    assert sidetone_device_to_percent(0) == 0
    assert sidetone_device_to_percent(255) == 100
    assert sidetone_device_to_percent(sidetone_percent_to_device(50)) == 50


def test_epos_device_live_protocol_with_mock_transport(tmp_path: Path) -> None:
    cache = StateCache(path=tmp_path / "state.json")
    transport = MockHidTransport(auto_reply=True)

    with transport:
        dev = EposDevice(transport, cache=cache)
        st = dev.read_status()
        assert st.connected is True
        assert st.battery_percent == 100
        assert st.battery_mv == 4158
        assert st.firmware_version == "1.3.5"
        assert st.anc_enabled is False
        assert st.voice_prompts == "off"
        assert st.sidetone_level == 35
        assert st.mic_noise_filter is True
        assert st.auto_sleep is True

        dev.set_sidetone(50)
        dev.set_mic_noise_filter(False)
        dev.set_auto_sleep(False)
        dev.set_voice_prompts("voice")

        st2 = dev.read_status()
        assert st2.sidetone_level == 50
        assert st2.mic_noise_filter is False
        assert st2.auto_sleep is False
        assert st2.voice_prompts == "voice"

        dev.set_voice_prompts("tones")
        st3 = dev.read_status()
        assert st3.voice_prompts == "tones"
