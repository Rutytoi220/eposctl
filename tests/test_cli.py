"""Unit tests for `eposctl` CLI, Waybar JSON formatting, and PipeWire configs."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from eposctl.cli import app
from eposctl.constants import EQ_PROFILES
from eposctl.protocol import DeviceTelemetry
from eposctl.tones import resolve_chime_sink
from eposctl.waybar import format_waybar_payload

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parent.parent


def test_waybar_payload_disconnected() -> None:
    payload = format_waybar_payload(DeviceTelemetry(connected=False))
    assert payload["alt"] == "disconnected"
    assert payload["class"] == "disconnected"
    assert payload["percentage"] == 0
    assert "offline" in payload["text"].lower()


def test_waybar_payload_connected_states() -> None:
    state = DeviceTelemetry(
        connected=True,
        connection_mode="wired",
        battery_percent=12,
        charging=False,
        anc_enabled=True,
        mic_muted=True,
        mic_noise_filter=True,
        sidetone_level=25,
        auto_sleep=True,
        eq_profile="esports",
    )
    payload = format_waybar_payload(state)
    assert payload["percentage"] == 12
    assert "12%" in payload["text"]
    assert "ANC" in payload["text"]
    assert "MUTE" in payload["text"]
    assert "critical" in payload["class"]
    assert "anc-on" in payload["class"]
    assert "mic-muted" in payload["class"]
    assert "eq-esports" in payload["class"]
    assert "Sidetone: 25%" in payload["tooltip"]


def test_cli_status_json_mock() -> None:
    result = runner.invoke(app, ["status", "--json", "--mock"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    for key in ("text", "alt", "tooltip", "class", "percentage"):
        assert key in data
    assert data["percentage"] == 100
    assert "charging" in data["class"]


def test_cli_controls_mock() -> None:
    r1 = runner.invoke(app, ["sidetone", "55", "--mock"])
    assert r1.exit_code == 0
    assert "55%" in r1.stdout

    r2 = runner.invoke(app, ["sidetone", "off", "--mock"])
    assert r2.exit_code == 0
    assert "off" in r2.stdout.lower()

    r3 = runner.invoke(app, ["sleep", "on", "--mock"])
    assert r3.exit_code == 0

    r4 = runner.invoke(app, ["mic-noise-filter", "on", "--mock"])
    assert r4.exit_code == 0

    r_vp = runner.invoke(app, ["voice-prompts", "tones", "--mock"])
    assert r_vp.exit_code == 0
    assert "0x07/0x01" in r_vp.stdout

    r5 = runner.invoke(app, ["eq", "music", "--dry-run"])
    assert r5.exit_code == 0
    assert "epos_h3pro_eq_music" in r5.stdout

    r_bad = runner.invoke(app, ["sleep", "99", "--mock"])
    assert r_bad.exit_code == 2


def test_pipewire_configs_present_and_valid() -> None:
    pw_dir = REPO_ROOT / "pipewire"
    for prof in EQ_PROFILES:
        conf = pw_dir / f"epos-eq-{prof}.conf"
        assert conf.exists(), f"Missing PipeWire config: {conf}"
        text = conf.read_text(encoding="utf-8")
        assert "libpipewire-module-filter-chain" in text
        assert f"epos_h3pro_eq_{prof}" in text
        assert "alsa_output.usb-1395_EPOS_H3PRO_0123456789ABCDEF-00.iec958-stereo" in text


def test_dynamic_chime_sink_resolution() -> None:
    sinks = [
        ("alsa_output.pci-0000_00_1f.3.HiFi__Headphones__sink", "SUSPENDED"),
        ("alsa_output.usb-1395_EPOS_GSA70_Dongle-00.analog-stereo", "IDLE"),
    ]
    assert resolve_chime_sink(prefer_epos=True, sinks_override=sinks) == (
        "alsa_output.usb-1395_EPOS_GSA70_Dongle-00.analog-stereo"
    )
    # Disconnect chime should always fall back to @DEFAULT_SINK@ (laptop speakers)
    assert resolve_chime_sink(prefer_epos=False, sinks_override=sinks) == "@DEFAULT_SINK@"
    # When no EPOS sink is present, fall back to @DEFAULT_SINK@
    assert resolve_chime_sink(
        prefer_epos=True,
        sinks_override=[("alsa_output.pci-0000_00_1f.3.HiFi__Headphones__sink", "RUNNING")],
    ) == "@DEFAULT_SINK@"


def test_systemd_and_waybar_assets_exist() -> None:
    svc = REPO_ROOT / "systemd" / "eposctl-watch.service"
    assert svc.exists()
    svc_text = svc.read_text(encoding="utf-8")
    assert "eposctl watch" in svc_text
    assert "pipewire.service" in svc_text

    wb = REPO_ROOT / "waybar" / "epos-h3pro.jsonc"
    assert wb.exists()
    assert "eposctl status --json" in wb.read_text(encoding="utf-8")
