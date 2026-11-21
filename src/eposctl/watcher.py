"""USB hotplug & HID event watcher state machine for `eposctl watch`.

Handles:
  - udev `uaccess` ACL race on USB replug (retries HidPermissionError for up to 2.0s)
  - PipeWire sink readiness wait on replug (polls up to 2.5s + 150ms DAC settle)
  - WirePlumber default-sink switchover delay (300ms) on USB unplug
  - Preserving `"tones"` mode across unplug/replug cycles
  - Live ANC toggle & Bluetooth button chimes in `"tones"` mode
"""

from __future__ import annotations

import time
from typing import Callable

from eposctl.protocol import DeviceTelemetry, EposDevice, StateCache
from eposctl.tones import play_tone, wait_for_epos_sink
from eposctl.transport import (
    HidPermissionError,
    HidTransport,
    HidTransportError,
)


class HotplugWatcher:
    """Testable hotplug state machine for wired EPOS H3PRO Hybrid (`1395:0101`)."""

    def __init__(
        self,
        transport: HidTransport,
        cache: StateCache | None = None,
        play_fn: Callable[..., bool] = play_tone,
        wait_sink_fn: Callable[[], str] = wait_for_epos_sink,
        sleep_fn: Callable[[float], None] = time.sleep,
        log_fn: Callable[[str], None] = print,
        udev_retry_s: float = 2.0,
        udev_poll_s: float = 0.15,
        disconnect_settle_s: float = 0.3,
    ) -> None:
        self.transport = transport
        self.cache = cache or StateCache()
        self.play_fn = play_fn
        self.wait_sink_fn = wait_sink_fn
        self.sleep_fn = sleep_fn
        self.log_fn = log_fn
        self.udev_retry_s = udev_retry_s
        self.udev_poll_s = udev_poll_s
        self.disconnect_settle_s = disconnect_settle_s

        self.was_connected: bool = False
        self.initialized: bool = False
        self.state: DeviceTelemetry = DeviceTelemetry()

    def _persisted_prompt_mode(self) -> str:
        return str(self.cache.load().get("voice_prompts") or "off")

    def _open_with_udev_retry(self) -> bool:
        """Open HID transport, retrying HidPermissionError while systemd-udevd applies uaccess."""
        deadline = time.monotonic() + self.udev_retry_s
        while True:
            try:
                self.transport.open()
                return True
            except HidPermissionError:
                if time.monotonic() >= deadline:
                    return False
                self.sleep_fn(self.udev_poll_s)
            except HidTransportError:
                return False

    def _handle_disconnect(self) -> None:
        self.transport.close()
        if self.was_connected:
            self.was_connected = False
            mode = self._persisted_prompt_mode()
            self.log_fn("Headset unplugged — waiting for USB reconnect...")
            if mode == "tones":
                if self.disconnect_settle_s > 0:
                    self.sleep_fn(self.disconnect_settle_s)
                self.play_fn("disconnect", target_sink="@DEFAULT_SINK@", blocking=True)

    def step(self) -> None:
        """Execute one iteration of the hotplug & event polling loop."""
        if not self.transport.is_open():
            if not self._open_with_udev_retry():
                if self.was_connected:
                    self._handle_disconnect()
                self.initialized = True
                return

            desired_mode = self._persisted_prompt_mode()
            dev = EposDevice(self.transport, cache=self.cache)
            try:
                self.state = dev.read_status(poll_timeout_ms=250, query_hardware=True)
                # Preserve `"tones"` mode across USB replug (re-silence hw voice if needed)
                if desired_mode == "tones":
                    if self.state.voice_prompts != "tones":
                        dev.set_voice_prompts("tones")
                        self.state.voice_prompts = "tones"
            except HidTransportError:
                self._handle_disconnect()
                return

            is_replug = self.initialized and not self.was_connected
            self.was_connected = True
            self.initialized = True
            self.log_fn(
                f"Connected (Prompts={self.state.voice_prompts}, Battery={self.state.battery_percent}%)"
            )

            if is_replug and self._persisted_prompt_mode() == "tones":
                sink = self.wait_sink_fn()
                ok = self.play_fn("connect", target_sink=sink, blocking=True)
                self.log_fn(f"Chime: connect -> {sink} (ok={ok})")
            return

        dev = EposDevice(self.transport, cache=self.cache)
        prev_anc = self.state.anc_enabled
        prev_ev = self.state.last_consumer_event
        try:
            dev.poll_events(self.state, poll_timeout_ms=150)
        except HidTransportError:
            self._handle_disconnect()
            return

        if self._persisted_prompt_mode() == "tones":
            if self.state.anc_enabled != prev_anc and self.state.anc_enabled is not None:
                tone = "anc_on" if self.state.anc_enabled else "anc_off"
                ok = self.play_fn(tone)
                self.log_fn(f"Chime: {tone} (ok={ok})")
            elif self.state.last_consumer_event == "bt_pair" and self.state.last_consumer_event != prev_ev:
                ok = self.play_fn("bt_pair")
                self.log_fn(f"Chime: bt_pair (ok={ok})")
