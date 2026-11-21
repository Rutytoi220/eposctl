"""Keyboard-driven Textual TUI for EPOS H3PRO Hybrid (`eposctl tui`)."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, ProgressBar, Static

from eposctl.constants import EQ_PROFILES, VOICE_PROMPT_MODES
from eposctl.pipewire import PipeWireError, apply_eq_profile, detect_active_eq_profile
from eposctl.tones import play_tone
from eposctl.protocol import (
    CMD_AUTO_SLEEP_GET,
    CMD_BATTERY_GET,
    CMD_MIC_NOISE_FILTER_GET,
    CMD_SIDETONE_GET,
    DeviceTelemetry,
    EposDevice,
    StateCache,
    build_mock_reply_frame,
)
from eposctl.transport import (
    HidTransport,
    HidTransportError,
    HidrawTransport,
    MockHidTransport,
)

# 2D focus grid for Vim (h/j/k/l) and Arrow-key navigation
CONTROL_GRID: list[list[str]] = [
    ["st-off", "st-down", "st-up", "st-max"],
    ["vp-voice", "vp-tones", "vp-off"],
    ["nf-off", "nf-on"],
    ["sleep-off", "sleep-on"],
    ["eq-off", *[f"eq-{p}" for p in EQ_PROFILES]],
]


class EposTuiApp(App[None]):
    """Interactive Textual control panel for the EPOS H3PRO Hybrid."""

    TITLE = "eposctl — EPOS H3PRO Hybrid"
    SUB_TITLE = "Hardware Control (0xEB 0xFE) & PipeWire DSP"

    CSS = """
    Screen {
        layout: vertical;
    }
    #main-scroll {
        height: 1fr;
        padding: 0 2;
    }
    .panel {
        height: auto;
        border: round $accent;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 0 2;
        margin-top: 1;
    }
    .row {
        height: auto;
        align: left middle;
        margin: 0;
    }
    .label {
        width: 18;
        text-style: bold;
    }
    #st-value {
        width: 7;
        content-align: center middle;
        text-style: bold;
    }
    #battery-bar {
        width: 24;
    }
    Button {
        min-width: 7;
        margin-right: 1;
    }
    Button.-active {
        background: $success;
        color: $text;
    }
    Button:focus {
        background: $warning;
        color: $background;
        text-style: bold;
    }
    #status-log {
        height: 3;
        color: $text-muted;
        border: solid $surface-lighten-2;
        padding: 0 1;
        margin: 0 2;
    }
    """

    BINDINGS = [
        Binding("h", "nav_left", "hjkl/Arrows: Move"),
        Binding("left", "nav_left", "Left", show=False),
        Binding("l", "nav_right", "Right", show=False),
        Binding("right", "nav_right", "Right", show=False),
        Binding("j", "nav_down", "Down", show=False),
        Binding("down", "nav_down", "Down", show=False),
        Binding("k", "nav_up", "Up", show=False),
        Binding("up", "nav_up", "Up", show=False),
        Binding("enter", "activate_focused", "Select", show=True),
        Binding("[", "sidetone_down", "Sidetone -5%"),
        Binding("]", "sidetone_up", "Sidetone +5%"),
        Binding("r", "query_hardware", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, mock: bool = False) -> None:
        super().__init__()
        self.mock = mock
        self._transport: HidTransport | None = None
        self._device: EposDevice | None = None
        self._state = DeviceTelemetry()
        self._row = 0
        self._col = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with VerticalScroll(id="main-scroll"):
            with Vertical(classes="panel", id="telemetry-panel") as tel_panel:
                tel_panel.border_title = "Device Telemetry (Live HID)"
                yield Static("Initializing...", id="device-summary")
                with Horizontal(classes="row"):
                    yield Static("Battery", classes="label")
                    yield ProgressBar(total=100, show_eta=False, id="battery-bar")
                    yield Static(" --%", id="battery-label")
                yield Static("ANC: --  |  Mic Filter: --  |  EQ: --", id="flags-summary")

            with Vertical(classes="panel", id="hardware-panel") as hw_panel:
                hw_panel.border_title = "Hardware Controls (Verified 0xEB 0xFE)"
                with Horizontal(classes="row"):
                    yield Static("Sidetone", classes="label")
                    yield Button("Off", id="st-off", compact=True)
                    yield Button("-10%", id="st-down", compact=True)
                    yield Static("Off", id="st-value")
                    yield Button("+10%", id="st-up", compact=True)
                    yield Button("Max", id="st-max", compact=True)

                with Horizontal(classes="row"):
                    yield Static("Prompts", classes="label")
                    yield Button("Voice", id="vp-voice", compact=True)
                    yield Button("Tones", id="vp-tones", compact=True)
                    yield Button("Off", id="vp-off", compact=True)

                with Horizontal(classes="row"):
                    yield Static("Mic Noise Filter", classes="label")
                    yield Button("Off", id="nf-off", compact=True)
                    yield Button("On", id="nf-on", compact=True)

                with Horizontal(classes="row"):
                    yield Static("Auto-Sleep", classes="label")
                    yield Button("Off", id="sleep-off", compact=True)
                    yield Button("On", id="sleep-on", compact=True)

            with Vertical(classes="panel", id="eq-panel") as eq_panel:
                eq_panel.border_title = "PipeWire EQ Profile (filter-chain)"
                with Horizontal(classes="row"):
                    yield Button("Off", id="eq-off", compact=True)
                    for prof in EQ_PROFILES:
                        yield Button(prof.capitalize(), id=f"eq-{prof}", compact=True)

        yield Static("Ready. Use h/j/k/l or arrows to navigate, Enter to select.", id="status-log")
        yield Footer()

    def on_mount(self) -> None:
        if self.mock:
            self._transport = MockHidTransport(auto_reply=True)
            self._transport.open()
            self._log("Running in --mock mode.")
        else:
            self._transport = HidrawTransport(read_only=False)
            try:
                self._transport.open()
                self._log("Connected to EPOS H3PRO Hybrid. Use h/j/k/l + Enter.")
            except HidTransportError as exc:
                self._log(f"HID unavailable: {exc}")

        self._device = EposDevice(
            self._transport,
            cache=StateCache(enabled=not self.mock),
        )
        self.action_query_hardware()
        self._focus_grid_cell(0, 0)
        # Fast async event polling (ANC slider, volume, BT) + periodic battery refresh
        self.set_interval(0.2, self._poll_async_events)
        self.set_interval(15.0, self.action_query_hardware)

    def on_unmount(self) -> None:
        if self._transport is not None:
            self._transport.close()

    def _focus_grid_cell(self, row: int, col: int) -> None:
        self._row = max(0, min(len(CONTROL_GRID) - 1, row))
        row_ids = CONTROL_GRID[self._row]
        self._col = max(0, min(len(row_ids) - 1, col))
        widget = self.query_one(f"#{row_ids[self._col]}")
        widget.focus()
        widget.scroll_visible()

    def _sync_grid_from_focus(self) -> None:
        focused = self.focused
        if focused is None or not focused.id:
            return
        for r_idx, row_ids in enumerate(CONTROL_GRID):
            if focused.id in row_ids:
                self._row = r_idx
                self._col = row_ids.index(focused.id)
                return

    def action_nav_left(self) -> None:
        self._sync_grid_from_focus()
        row_len = len(CONTROL_GRID[self._row])
        self._focus_grid_cell(self._row, (self._col - 1) % row_len)

    def action_nav_right(self) -> None:
        self._sync_grid_from_focus()
        row_len = len(CONTROL_GRID[self._row])
        self._focus_grid_cell(self._row, (self._col + 1) % row_len)

    def action_nav_down(self) -> None:
        self._sync_grid_from_focus()
        next_row = (self._row + 1) % len(CONTROL_GRID)
        self._focus_grid_cell(next_row, self._col)

    def action_nav_up(self) -> None:
        self._sync_grid_from_focus()
        prev_row = (self._row - 1) % len(CONTROL_GRID)
        self._focus_grid_cell(prev_row, self._col)

    def action_activate_focused(self) -> None:
        focused = self.focused
        if isinstance(focused, Button):
            focused.press()

    def _log(self, message: str) -> None:
        self.query_one("#status-log", Static).update(message)

    def _try_reconnect(self) -> bool:
        if self.mock or self._transport is None:
            return False
        try:
            self._transport.close()
            self._transport.open()
            self._log("Reconnected to EPOS H3PRO Hybrid.")
            if self._state.voice_prompts == "tones":
                play_tone("connect")
            return True
        except HidTransportError:
            return False

    def _handle_disconnect(self) -> None:
        if self._transport is not None:
            self._transport.close()
        self._state.connected = False
        self._state.connection_mode = "disconnected"
        self._state.battery_percent = None
        self._state.battery_mv = None
        self._state.charging = None
        self._state.anc_enabled = None
        self._state.telemetry_endpoint = None
        self._log("Headset unplugged — waiting for USB reconnect...")
        self._render_state()

    def action_query_hardware(self) -> None:
        """Full live hardware poll (battery, sidetone, mic filter, auto-sleep)."""
        if self._device is None or self._transport is None:
            return
        if not self._transport.is_open():
            if not self._try_reconnect():
                self._state.connected = False
                self._state.connection_mode = "disconnected"
                self._render_state()
                return
        try:
            self._state = self._device.read_status(poll_timeout_ms=200, query_hardware=True)
            self._state.eq_profile = detect_active_eq_profile(
                cache=StateCache(enabled=not self.mock)
            )
            self._render_state()
        except HidTransportError:
            self._handle_disconnect()

    def _poll_async_events(self) -> None:
        """Lightweight non-blocking drain for physical ANC slider & button events."""
        if self._device is None or self._transport is None:
            return
        if not self._transport.is_open():
            if self._try_reconnect():
                self.action_query_hardware()
            return
        prev_anc = self._state.anc_enabled
        prev_ev = self._state.last_consumer_event
        try:
            self._device.poll_events(self._state, poll_timeout_ms=5)
        except HidTransportError:
            self._handle_disconnect()
            return

        if self._state.anc_enabled != prev_anc and self._state.anc_enabled is not None:
            self._log(f"Hardware event: ANC switched {'ON' if self._state.anc_enabled else 'OFF'}.")
            if self._state.voice_prompts == "tones" and not self.mock:
                play_tone("anc_on" if self._state.anc_enabled else "anc_off")
            self._render_state()
        elif self._state.last_consumer_event and self._state.last_consumer_event != prev_ev:
            self._log(f"Hardware event: {self._state.last_consumer_event}")
            if self._state.last_consumer_event == "bt_pair" and self._state.voice_prompts == "tones" and not self.mock:
                play_tone("bt_pair")

    def _render_state(self) -> None:
        s = self._state
        ep_info = f"({s.telemetry_endpoint or 'no-hid'})"
        conn = "Connected" if s.connected else "Disconnected"
        self.query_one("#device-summary", Static).update(
            f"{s.device_name} — {conn} [{s.connection_mode}] {ep_info}"
        )

        pct = s.battery_percent if s.battery_percent is not None else 0
        bar = self.query_one("#battery-bar", ProgressBar)
        bar.update(progress=pct)
        if s.battery_percent is not None:
            pct_text = f" {s.battery_percent}%"
            if s.charging:
                pct_text += " (Charging)"
        else:
            pct_text = " --%"
        self.query_one("#battery-label", Static).update(pct_text)

        anc = "ON" if s.anc_enabled is True else ("OFF" if s.anc_enabled is False else "Unknown")
        nf = "ON" if s.mic_noise_filter is True else ("OFF" if s.mic_noise_filter is False else "Unknown")
        self.query_one("#flags-summary", Static).update(
            f"ANC: {anc}  |  Mic Filter: {nf}  |  EQ: {s.eq_profile.upper()}"
        )

        st_label = "Off" if s.sidetone_level == 0 else f" {s.sidetone_level}% "
        self.query_one("#st-value", Static).update(st_label)

        for mode in VOICE_PROMPT_MODES:
            self.query_one(f"#vp-{mode}", Button).set_class(s.voice_prompts == mode, "-active")

        self.query_one("#nf-off", Button).set_class(s.mic_noise_filter is False, "-active")
        self.query_one("#nf-on", Button).set_class(s.mic_noise_filter is True, "-active")

        self.query_one("#sleep-off", Button).set_class(s.auto_sleep is False, "-active")
        self.query_one("#sleep-on", Button).set_class(s.auto_sleep is True, "-active")

        for prof in ("off", *EQ_PROFILES):
            btn = self.query_one(f"#eq-{prof}", Button)
            btn.set_class(s.eq_profile == prof, "-active")

    def _apply_sidetone(self, level: int) -> None:
        level = max(0, min(100, level))
        if self._device is None:
            return
        try:
            self._device.set_sidetone(level)
            self._state.sidetone_level = level
            self._render_state()
            self._log(f"Hardware sidetone set to {'Off' if level == 0 else f'{level}%'}.")
        except HidTransportError as exc:
            self._log(f"Sidetone failed: {exc}")

    def action_sidetone_down(self) -> None:
        self._apply_sidetone(self._state.sidetone_level - 5)

    def action_sidetone_up(self) -> None:
        self._apply_sidetone(self._state.sidetone_level + 5)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "st-off":
            self._apply_sidetone(0)
        elif bid == "st-down":
            self._apply_sidetone(self._state.sidetone_level - 10)
        elif bid == "st-up":
            self._apply_sidetone(self._state.sidetone_level + 10)
        elif bid == "st-max":
            self._apply_sidetone(100)
        elif bid in ("vp-voice", "vp-tones", "vp-off") and self._device is not None:
            mode = bid.split("-", 1)[1]
            try:
                self._device.set_voice_prompts(mode)
                self._state.voice_prompts = mode
                self._render_state()
                if mode == "tones" and not self.mock:
                    play_tone("connect")
                desc = {
                    "voice": "Voice (hw spoken prompts)",
                    "tones": "Tones (hw voice OFF + PipeWire SFX chimes)",
                    "off": "Off (silent)",
                }[mode]
                self._log(f"Prompts set to {desc}.")
            except HidTransportError:
                self._handle_disconnect()
        elif bid in ("nf-off", "nf-on") and self._device is not None:
            enabled = bid == "nf-on"
            try:
                self._device.set_mic_noise_filter(enabled)
                self._state.mic_noise_filter = enabled
                self._render_state()
                self._log(f"Hardware mic noise filter set to {'ON' if enabled else 'OFF'}.")
            except HidTransportError as exc:
                self._log(f"Mic noise filter failed: {exc}")
        elif bid in ("sleep-off", "sleep-on") and self._device is not None:
            enabled = bid == "sleep-on"
            try:
                self._device.set_auto_sleep(enabled)
                self._state.auto_sleep = enabled
                self._render_state()
                self._log(f"Hardware auto-sleep set to {'ON' if enabled else 'OFF'}.")
            except HidTransportError as exc:
                self._log(f"Auto-sleep failed: {exc}")
        elif bid.startswith("eq-"):
            prof = bid.split("-", 1)[1]
            try:
                res = apply_eq_profile(
                    prof,
                    cache=StateCache(enabled=not self.mock),
                    dry_run=self.mock,
                )
                self._state.eq_profile = prof
                self._render_state()
                self._log(f"PipeWire EQ set to '{prof}' -> {res['sink']}.")
            except (PipeWireError, ValueError) as exc:
                self._log(f"EQ switch failed: {exc}")
