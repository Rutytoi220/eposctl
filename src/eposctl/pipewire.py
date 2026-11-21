"""Native PipeWire filter-chain EQ profile manager for EPOS H3PRO Hybrid.

Switches between the direct EPOS H3PRO ALSA output sink ('off') and low-latency
PipeWire filter-chain virtual sinks ('flat', 'esports', 'music', 'movie').
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from eposctl.constants import EPOS_PIPEWIRE_TARGET_NODE, EQ_PROFILES
from eposctl.protocol import StateCache


class PipeWireError(RuntimeError):
    """Raised when PipeWire / pactl operations fail."""


def _default_profiles_dir() -> Path:
    # Locate repo/package pipewire/ directory
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "pipewire",
        Path.home() / ".config" / "pipewire" / "pipewire.conf.d",
    ]
    for path in candidates:
        if path.is_dir() and any(path.glob("epos-eq-*.conf")):
            return path
    return candidates[0]


def _pid_file() -> Path:
    return Path.home() / ".cache" / "eposctl" / "filter-chain.pid"


def sink_name_for_profile(profile: str) -> str:
    return f"epos_h3pro_eq_{profile}"


def config_path_for_profile(profile: str, profiles_dir: Path | None = None) -> Path:
    base = profiles_dir or _default_profiles_dir()
    return base / f"epos-eq-{profile}.conf"


def _run_pactl(*args: str) -> str:
    try:
        proc = subprocess.run(
            ["pactl", *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout
    except FileNotFoundError as exc:
        raise PipeWireError("`pactl` not found. Install pipewire-pulse / libpulse.") from exc
    except subprocess.CalledProcessError as exc:
        raise PipeWireError(f"`pactl {' '.join(args)}` failed: {exc.stderr.strip()}") from exc


def list_sinks() -> list[str]:
    """Return PipeWire sink names via `pactl list short sinks`."""
    output = _run_pactl("list", "short", "sinks")
    sinks: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            sinks.append(parts[1].strip())
    return sinks


def find_epos_hardware_sink(sinks: list[str] | None = None) -> str:
    """Find the active EPOS H3PRO ALSA hardware sink name."""
    candidates = sinks if sinks is not None else list_sinks()
    if EPOS_PIPEWIRE_TARGET_NODE in candidates:
        return EPOS_PIPEWIRE_TARGET_NODE
    for s in candidates:
        if "1395_EPOS_H3PRO" in s and not s.startswith("epos_h3pro_eq_"):
            return s
    for s in candidates:
        if "EPOS" in s.upper() and not s.startswith("epos_h3pro_eq_"):
            return s
    return EPOS_PIPEWIRE_TARGET_NODE


def get_default_sink() -> str:
    return _run_pactl("get-default-sink").strip()


def move_active_streams(target_sink: str) -> int:
    """Move all active playback streams (sink-inputs) to target_sink."""
    output = _run_pactl("list", "short", "sink-inputs")
    moved = 0
    for line in output.splitlines():
        parts = line.split("\t")
        if parts and parts[0].strip().isdigit():
            stream_id = parts[0].strip()
            try:
                _run_pactl("move-sink-input", stream_id, target_sink)
                moved += 1
            except PipeWireError:
                pass
    return moved


def stop_managed_filter_chain() -> bool:
    """Stop any background `pipewire -c` filter-chain instance spawned by eposctl."""
    pf = _pid_file()
    if not pf.exists():
        return False
    try:
        pid = int(pf.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGTERM)
        pf.unlink(missing_ok=True)
        return True
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        pf.unlink(missing_ok=True)
        return False


def _spawn_filter_chain(conf_path: Path) -> int:
    """Launch a detached `pipewire -c <conf>` filter-chain process and record its PID."""
    stop_managed_filter_chain()
    pf = _pid_file()
    pf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        ["pipewire", "-c", str(conf_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    pf.write_text(f"{proc.pid}\n", encoding="utf-8")
    return proc.pid


def detect_active_eq_profile(cache: StateCache | None = None) -> str:
    """Detect the currently active EQ profile from PipeWire default sink or cache."""
    try:
        default_sink = get_default_sink()
        for profile in EQ_PROFILES:
            if default_sink == sink_name_for_profile(profile):
                return profile
        if "1395_EPOS" in default_sink or "EPOS_H3PRO" in default_sink:
            return "off"
    except PipeWireError:
        pass
    state = (cache or StateCache()).load()
    return str(state.get("eq_profile", "off"))


def apply_eq_profile(
    profile: str,
    profiles_dir: Path | None = None,
    cache: StateCache | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Activate a PipeWire EQ profile ('flat'|'esports'|'music'|'movie'|'off')."""
    normalized = profile.strip().lower()
    allowed = (*EQ_PROFILES, "off")
    if normalized not in allowed:
        raise ValueError(f"Unknown EQ profile '{profile}'. Allowed: {', '.join(allowed)}.")

    state_cache = cache or StateCache()

    if normalized == "off":
        hw_sink = EPOS_PIPEWIRE_TARGET_NODE if dry_run else find_epos_hardware_sink()
        if not dry_run:
            _run_pactl("set-default-sink", hw_sink)
            move_active_streams(hw_sink)
            stop_managed_filter_chain()
        cached = state_cache.load()
        cached["eq_profile"] = "off"
        state_cache.save(cached)
        return {"profile": "off", "sink": hw_sink, "spawned_pid": None}

    conf_path = config_path_for_profile(normalized, profiles_dir=profiles_dir)
    if not conf_path.exists():
        raise PipeWireError(f"PipeWire EQ config not found: {conf_path}")

    target_sink = sink_name_for_profile(normalized)
    spawned_pid: int | None = None

    if not dry_run:
        sinks = list_sinks()
        if target_sink not in sinks:
            spawned_pid = _spawn_filter_chain(conf_path)
            # Wait briefly for PipeWire to register the virtual filter-chain sink
            for _ in range(20):
                time.sleep(0.1)
                if target_sink in list_sinks():
                    break
            else:
                raise PipeWireError(
                    f"Filter-chain sink '{target_sink}' did not appear in PipeWire after launching {conf_path}."
                )

        _run_pactl("set-default-sink", target_sink)
        move_active_streams(target_sink)

    cached = state_cache.load()
    cached["eq_profile"] = normalized
    state_cache.save(cached)
    return {"profile": normalized, "sink": target_sink, "spawned_pid": spawned_pid}
