"""Unit tests for USB hotplug state machine (`HotplugWatcher`)."""

from __future__ import annotations

from pathlib import Path

from eposctl.protocol import StateCache
from eposctl.transport import HidPermissionError, HidTransportError, MockHidTransport
from eposctl.watcher import HotplugWatcher


class FlakyHotplugTransport(MockHidTransport):
    """Mock transport simulating USB unplug (EIO) and udev ACL permission race on replug."""

    def __init__(self) -> None:
        super().__init__(auto_reply=True)
        self.fail_reads: bool = False
        self.permission_errors_remaining: int = 0

    def open(self) -> None:
        if self.permission_errors_remaining > 0:
            self.permission_errors_remaining -= 1
            raise HidPermissionError("udev uaccess not applied yet")
        super().open()

    def read_telemetry(self, timeout_ms: int = 100, size: int = 128) -> bytes | None:
        if self.fail_reads:
            raise HidTransportError("HID read error: [Errno 5] Input/output error")
        return super().read_telemetry(timeout_ms=timeout_ms, size=size)


def test_hotplug_tones_mode_fires_disconnect_and_reconnect_chimes(tmp_path: Path) -> None:
    cache = StateCache(path=tmp_path / "state.json")
    cache.save({"voice_prompts": "tones"})

    tr = FlakyHotplugTransport()
    played: list[tuple[str, str | None, bool]] = []

    def fake_play(name: str, target_sink: str | None = None, blocking: bool = False, **_kw) -> bool:
        played.append((name, target_sink, blocking))
        return True

    watcher = HotplugWatcher(
        transport=tr,
        cache=cache,
        play_fn=fake_play,
        wait_sink_fn=lambda: "alsa_output.usb-1395_EPOS_H3PRO_0123456789ABCDEF-00.iec958-stereo",
        sleep_fn=lambda _s: None,
        log_fn=lambda _m: None,
    )

    # 1. Initial connection on service start (no spurious chime)
    watcher.step()
    assert watcher.was_connected is True
    assert played == []

    # 2. Simulate USB unplug (EIO on poll) -> plays 'disconnect' to @DEFAULT_SINK@
    tr.fail_reads = True
    watcher.step()
    assert watcher.was_connected is False
    assert played == [("disconnect", "@DEFAULT_SINK@", True)]

    # 3. Simulate USB replug with 2 transient udev HidPermissionError retries + hw rebooted to voice(1)
    tr.fail_reads = False
    tr.permission_errors_remaining = 2
    tr._mock_state[(0x07, 0x05)] = (1,)  # headset rebooted to voice mode
    watcher.step()

    assert watcher.was_connected is True
    assert watcher.state.voice_prompts == "tones"
    # Re-silenced hardware voice back to mode 2!
    assert tr._mock_state[(0x07, 0x05)] == (2,)
    assert played == [
        ("disconnect", "@DEFAULT_SINK@", True),
        ("connect", "alsa_output.usb-1395_EPOS_H3PRO_0123456789ABCDEF-00.iec958-stereo", True),
    ]


def test_hotplug_silent_in_off_and_voice_modes(tmp_path: Path) -> None:
    for mode in ("off", "voice"):
        cache = StateCache(path=tmp_path / f"state_{mode}.json")
        cache.save({"voice_prompts": mode})
        tr = FlakyHotplugTransport()
        played: list[str] = []

        watcher = HotplugWatcher(
            transport=tr,
            cache=cache,
            play_fn=lambda name, **_kw: played.append(name) or True,
            wait_sink_fn=lambda: "epos_sink",
            sleep_fn=lambda _s: None,
            log_fn=lambda _m: None,
        )

        watcher.step()  # initial connect
        tr.fail_reads = True
        watcher.step()  # unplug
        tr.fail_reads = False
        watcher.step()  # replug
        assert played == [], f"Expected no host chimes in '{mode}' mode, got {played}"
