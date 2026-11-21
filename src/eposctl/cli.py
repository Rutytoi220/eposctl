"""CLI entrypoint for `eposctl` — EPOS H3PRO Hybrid Linux userspace driver & DSP suite."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from eposctl import __version__
from eposctl.constants import EQ_PROFILES
from eposctl.pipewire import PipeWireError, apply_eq_profile, detect_active_eq_profile
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
    HidDeviceNotFoundError,
    HidPermissionError,
    HidTransport,
    HidTransportError,
    HidrawTransport,
    MockHidTransport,
)
from eposctl.waybar import format_waybar_payload

app = typer.Typer(
    name="eposctl",
    help="Open-source Linux driver, Waybar telemetry, TUI & PipeWire DSP manager for EPOS H3PRO Hybrid.",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


def _create_transport(mock: bool, read_only: bool = False) -> HidTransport:
    if mock:
        return MockHidTransport(auto_reply=True)
    return HidrawTransport(read_only=read_only)


def _print_status_table(state: DeviceTelemetry, warning: str | None = None) -> None:
    table = Table(title=f"{state.device_name} — Status", show_header=False, box=None)
    table.add_column("Field", style="bold cyan", width=22)
    table.add_column("Value")

    conn_str = "[green]Connected[/green]" if state.connected else "[red]Disconnected[/red]"
    table.add_row("Connection", f"{conn_str} ({state.connection_mode})")
    if state.product_id is not None:
        table.add_row("USB VID:PID", f"1395:{state.product_id:04x}")
    if state.telemetry_endpoint or state.control_endpoint:
        table.add_row(
            "HID Endpoints",
            f"telemetry={state.telemetry_endpoint or 'N/A'}, control={state.control_endpoint or 'N/A'}",
        )

    if state.firmware_version:
        table.add_row("Firmware", f"v{state.firmware_version}")

    batt = f"{state.battery_percent}%" if state.battery_percent is not None else "Unknown"
    volt = f" / {state.battery_mv / 1000:.2f}V" if state.battery_mv else ""
    chg = "Charging" if state.charging is True else ("Discharging" if state.charging is False else "Unknown")
    table.add_row("Battery", f"{batt}{volt} ({chg})")

    anc = "On" if state.anc_enabled is True else ("Off" if state.anc_enabled is False else "Unknown")
    nf = "On" if state.mic_noise_filter is True else ("Off" if state.mic_noise_filter is False else "Unknown")
    slp = "On" if state.auto_sleep is True else ("Off" if state.auto_sleep is False else "Unknown")
    vp_labels = {"voice": "Voice (spoken)", "tones": "Tones (SFX chimes)", "off": "Off (silent)"}
    vp = vp_labels.get(state.voice_prompts or "", "Unknown")
    table.add_row("ANC", anc)
    table.add_row("Prompts", vp)
    table.add_row("Mic Noise Filter", nf)
    table.add_row("Sidetone", "Off" if state.sidetone_level == 0 else f"{state.sidetone_level}%")
    table.add_row("Auto-Sleep", slp)
    table.add_row("PipeWire EQ", state.eq_profile)

    console.print(table)
    if warning:
        err_console.print(f"[yellow]Note:[/yellow] {warning}")


@app.command()
def version() -> None:
    """Print eposctl version."""
    console.print(f"eposctl {__version__}")


@app.command()
def status(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Output Waybar-compatible JSON telemetry.",
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="Use mocked HID telemetry instead of opening /dev/hidraw*.",
    ),
) -> None:
    """Show live EPOS H3PRO Hybrid telemetry (human-readable or Waybar JSON)."""
    # Querying hardware over input3 requires O_RDWR so we can write 0xEB 0xFE requests
    transport = _create_transport(mock=mock, read_only=False)
    warning: str | None = None
    try:
        transport.open()
    except HidDeviceNotFoundError:
        pass
    except HidPermissionError as exc:
        warning = str(exc)

    try:
        device = EposDevice(transport, cache=StateCache(enabled=not mock))
        state = device.read_status()
        state.eq_profile = detect_active_eq_profile(cache=StateCache(enabled=not mock))
    finally:
        transport.close()

    if as_json:
        payload = format_waybar_payload(state)
        typer.echo(json.dumps(payload))
    else:
        _print_status_table(state, warning=warning)


@app.command()
def sidetone(
    level: str = typer.Argument(..., help="Sidetone level: 0-100 or 'off'."),
    mock: bool = typer.Option(False, "--mock", help="Simulate command without writing to hardware."),
) -> None:
    """Set hardware sidetone gain (0-100 or off)."""
    raw = level.strip().lower()
    if raw == "off":
        val = 0
    else:
        try:
            val = int(raw)
        except ValueError as exc:
            err_console.print(f"[red]Invalid sidetone value '{level}'. Use 0-100 or 'off'.[/red]")
            raise typer.Exit(code=2) from exc

    if not 0 <= val <= 100:
        err_console.print("[red]Sidetone must be between 0 and 100.[/red]")
        raise typer.Exit(code=2)

    transport = _create_transport(mock=mock, read_only=False)
    try:
        with transport:
            device = EposDevice(transport, cache=StateCache(enabled=not mock))
            frame = device.set_sidetone(val)
    except HidTransportError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    label = "off" if val == 0 else f"{val}%"
    console.print(f"[green]Sidetone set to {label}[/green] (verified 0x0A/0x0B, TX {len(frame)}B)")


@app.command("mic-noise-filter")
def mic_noise_filter(
    state: str = typer.Argument(..., help="Mic noise cancellation: 'on' or 'off'."),
    mock: bool = typer.Option(False, "--mock", help="Simulate command without writing to hardware."),
) -> None:
    """Toggle hardware microphone noise cancellation (0x0A/0x11)."""
    raw = state.strip().lower()
    if raw not in ("on", "off"):
        err_console.print("[red]Invalid value. Use 'on' or 'off'.[/red]")
        raise typer.Exit(code=2)
    enabled = raw == "on"

    transport = _create_transport(mock=mock, read_only=False)
    try:
        with transport:
            device = EposDevice(transport, cache=StateCache(enabled=not mock))
            frame = device.set_mic_noise_filter(enabled)
    except HidTransportError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Mic noise filter set to {raw}[/green] (verified 0x0A/0x11, TX {len(frame)}B)")


@app.command()
def sleep(
    state: str = typer.Argument(..., help="Auto-sleep low-power mode: 'on' or 'off'."),
    mock: bool = typer.Option(False, "--mock", help="Simulate command without writing to hardware."),
) -> None:
    """Toggle headset auto-sleep low-power mode (0x01/0x1F)."""
    raw = state.strip().lower()
    if raw not in ("on", "off"):
        err_console.print("[red]Invalid value. Use 'on' or 'off'.[/red]")
        raise typer.Exit(code=2)
    enabled = raw == "on"

    transport = _create_transport(mock=mock, read_only=False)
    try:
        with transport:
            device = EposDevice(transport, cache=StateCache(enabled=not mock))
            frame = device.set_auto_sleep(enabled)
    except HidTransportError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Auto-sleep set to {raw}[/green] (verified 0x01/0x1F, TX {len(frame)}B)")


@app.command("voice-prompts")
def voice_prompts(
    mode: str = typer.Argument(
        ...,
        help="Prompt preset: 'voice' (spoken), 'tones' (Tu-DU/Tu-di chimes, no voice), or 'off'.",
    ),
    mock: bool = typer.Option(False, "--mock", help="Simulate command without writing to hardware."),
) -> None:
    """Set prompt preset: voice, tones (PipeWire SFX + hw voice off), or off."""
    from eposctl.tones import play_tone

    raw = mode.strip().lower()
    if raw == "on":
        raw = "voice"
    if raw not in ("voice", "tones", "off"):
        err_console.print("[red]Invalid value. Use 'voice', 'tones', or 'off'.[/red]")
        raise typer.Exit(code=2)

    transport = _create_transport(mock=mock, read_only=False)
    try:
        with transport:
            device = EposDevice(transport, cache=StateCache(enabled=not mock))
            frame = device.set_voice_prompts(raw)
    except (ValueError, HidTransportError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if raw == "tones" and not mock:
        play_tone("connect")

    desc = {
        "voice": "Voice (spoken)",
        "tones": "Tones (SFX chimes only — hw voice off)",
        "off": "Off (silent)",
    }[raw]
    console.print(f"[green]Prompts set to {desc}[/green] (0x07/0x01, TX {len(frame)}B)")


@app.command()
def watch() -> None:
    """Background watcher that plays 'Tu-DU' / 'Tu-di' chimes in Tones mode on USB/ANC/BT events."""
    import signal
    import time

    from eposctl.watcher import HotplugWatcher

    stop = False

    def _sig(_s, _f):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    console.print("[cyan]eposctl watch[/cyan]: Listening for EPOS H3PRO USB/ANC/BT events (Ctrl+C to stop)...")
    transport = HidrawTransport(read_only=False)
    watcher = HotplugWatcher(
        transport=transport,
        cache=StateCache(),
        log_fn=lambda msg: console.print(msg),
    )

    try:
        while not stop:
            watcher.step()
            if not transport.is_open():
                time.sleep(0.35)
    finally:
        transport.close()


@app.command("test-tone")
def test_tone(
    name: str = typer.Argument(
        "connect",
        help="Chime to test: connect, disconnect, anc_on, anc_off, or bt_pair.",
    ),
) -> None:
    """Test synthesized PipeWire chime playback with dynamic sink routing."""
    from eposctl.tones import TONE_PATTERNS, play_tone, resolve_chime_sink

    key = name.strip().lower()
    if key not in TONE_PATTERNS:
        err_console.print(
            f"[red]Unknown tone '{name}'. Allowed: {', '.join(TONE_PATTERNS)}.[/red]"
        )
        raise typer.Exit(code=2)

    prefer_epos = key != "disconnect"
    sink = resolve_chime_sink(prefer_epos=prefer_epos)
    ok = play_tone(key, target_sink=sink, blocking=True)
    if not ok:
        err_console.print("[red]Failed to play tone (is `paplay` or `pw-play` installed?).[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Played '{key}' chime[/green] -> `{sink}`")


@app.command("install-service")
def install_service() -> None:
    """Install `~/.local/bin/eposctl` and enable `systemd --user` eposctl-watch.service."""
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent
    unit_src = repo_root / "systemd" / "eposctl-watch.service"
    if not unit_src.exists():
        err_console.print(f"[red]Service unit not found: {unit_src}[/red]")
        raise typer.Exit(code=1)

    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    target_bin = local_bin / "eposctl"

    # Point ~/.local/bin/eposctl at the active venv's eposctl entrypoint
    venv_bin = Path(sys.executable).parent / "eposctl"
    if venv_bin.exists() and venv_bin.resolve() != target_bin.resolve():
        if target_bin.exists() or target_bin.is_symlink():
            target_bin.unlink()
        target_bin.symlink_to(venv_bin)
        console.print(f"[green]Linked[/green] `{target_bin}` -> `{venv_bin}`")
    elif not target_bin.exists():
        err_console.print(f"[red]Could not locate eposctl binary at {venv_bin}.[/red]")
        raise typer.Exit(code=1)

    user_systemd = Path.home() / ".config" / "systemd" / "user"
    user_systemd.mkdir(parents=True, exist_ok=True)
    unit_dst = user_systemd / "eposctl-watch.service"
    shutil.copy2(unit_src, unit_dst)
    console.print(f"[green]Installed[/green] `{unit_dst}`")

    for args in (
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "eposctl-watch.service"],
    ):
        proc = subprocess.run(args, capture_output=True, text=True)
        if proc.returncode != 0:
            err_console.print(f"[red]Command failed:[/red] {' '.join(args)}\n{proc.stderr.strip()}")
            raise typer.Exit(code=1)

    console.print("[green]Enabled and started `eposctl-watch.service`![/green]")


@app.command()
def eq(
    profile: str = typer.Argument(
        ...,
        help=f"PipeWire EQ profile: {', '.join(EQ_PROFILES)}, or off.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate profile without calling pactl/pipewire.",
    ),
) -> None:
    """Activate or switch the PipeWire filter-chain EQ profile."""
    try:
        result = apply_eq_profile(
            profile,
            cache=StateCache(enabled=not dry_run),
            dry_run=dry_run,
        )
    except (ValueError, PipeWireError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    mode = " [dim](dry-run)[/dim]" if dry_run else ""
    console.print(
        f"[green]PipeWire EQ profile set to '{result['profile']}'[/green] "
        f"-> sink `{result['sink']}`{mode}"
    )


@app.command()
def tui(
    mock: bool = typer.Option(False, "--mock", help="Launch TUI with mocked HID device telemetry."),
) -> None:
    """Launch the interactive keyboard-driven Textual TUI."""
    from eposctl.tui import EposTuiApp

    EposTuiApp(mock=mock).run()


if __name__ == "__main__":
    app()
