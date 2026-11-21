"""Synthesized EPOS-style hardware chimes ("Tu-DU" / "Tu-di") played via PipeWire.

Used in `tones` prompt mode: the H3PRO Hybrid firmware's spoken voice prompts
are disabled (`0x07/0x01 = 2`), while PipeWire plays crisp, low-latency chimes
dynamically routed to the active EPOS H3PRO sink, or `@DEFAULT_SINK@` on USB
disconnect (laptop/system speakers).
"""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import time
import wave
from pathlib import Path

SAMPLE_RATE = 48000

# (freq_hz, duration_ms, volume_0_to_1) sequences
# Leading/trailing silence prevents PipeWire stream spin-up from clipping short chimes.
TONE_PATTERNS: dict[str, list[tuple[float, int, float]]] = {
    # Ascending "Tu-DU" (connect / confirm)
    "connect": [
        (0.0, 40, 0.0),
        (523.25, 110, 0.78),
        (0.0, 25, 0.0),
        (783.99, 180, 0.85),
        (0.0, 60, 0.0),
    ],
    # Descending "Tu-di" (disconnect)
    "disconnect": [
        (0.0, 40, 0.0),
        (659.25, 110, 0.78),
        (0.0, 25, 0.0),
        (440.0, 170, 0.75),
        (0.0, 60, 0.0),
    ],
    # Soft ascending chime (ANC ON)
    "anc_on": [
        (0.0, 35, 0.0),
        (587.33, 95, 0.72),
        (0.0, 20, 0.0),
        (739.99, 150, 0.80),
        (0.0, 50, 0.0),
    ],
    # Soft descending chime (ANC OFF)
    "anc_off": [
        (0.0, 35, 0.0),
        (739.99, 95, 0.72),
        (0.0, 20, 0.0),
        (587.33, 150, 0.75),
        (0.0, 50, 0.0),
    ],
    # Short double-pip (Bluetooth pair button)
    "bt_pair": [
        (0.0, 35, 0.0),
        (880.0, 75, 0.75),
        (0.0, 50, 0.0),
        (880.0, 75, 0.75),
        (0.0, 50, 0.0),
    ],
}


def _cache_dir() -> Path:
    return Path.home() / ".cache" / "eposctl" / "tones"


def _synthesize_wav(path: Path, pattern: list[tuple[float, int, float]]) -> None:
    """Generate a smooth, warm 16-bit stereo PCM WAV file for a chime sequence."""
    frames = bytearray()
    for freq, dur_ms, vol in pattern:
        n_samples = int(SAMPLE_RATE * dur_ms / 1000.0)
        fade_in = max(1, int(SAMPLE_RATE * 0.008))
        fade_out = max(1, int(SAMPLE_RATE * 0.020))
        for i in range(n_samples):
            if freq <= 0.0 or vol <= 0.0:
                sample = 0.0
            else:
                t = i / SAMPLE_RATE
                raw = 0.85 * math.sin(2.0 * math.pi * freq * t) + 0.15 * math.sin(
                    4.0 * math.pi * freq * t
                )
                env = 1.0
                if i < fade_in:
                    env = i / fade_in
                elif i > n_samples - fade_out:
                    env = max(0.0, (n_samples - i) / fade_out)
                sample = raw * vol * env
            val = max(-32767, min(32767, int(sample * 32767)))
            frames.extend(struct.pack("<hh", val, val))

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(frames))


def ensure_tone_wav(name: str) -> Path:
    """Return path to cached stereo WAV for `name`, synthesizing it on first use."""
    if name not in TONE_PATTERNS:
        raise ValueError(f"Unknown tone '{name}'. Allowed: {tuple(TONE_PATTERNS)}")
    path = _cache_dir() / f"{name}.wav"
    if not path.exists():
        _synthesize_wav(path, TONE_PATTERNS[name])
    return path


def _parse_short_sinks(output: str) -> list[tuple[str, str]]:
    """Parse `pactl list short sinks` output into [(sink_name, state), ...]."""
    result: list[tuple[str, str]] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            name = parts[1].strip()
            state = parts[-1].strip().upper() if len(parts) >= 5 else ""
            result.append((name, state))
    return result


def _query_short_sinks() -> list[tuple[str, str]]:
    try:
        proc = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            check=True,
            capture_output=True,
            text=True,
        )
        return _parse_short_sinks(proc.stdout)
    except (OSError, subprocess.CalledProcessError):
        return []


def is_epos_sink_name(name: str) -> bool:
    upper = name.upper()
    return any(tok in upper for tok in ("1395", "EPOS", "H3PRO"))


def resolve_chime_sink(
    prefer_epos: bool = True,
    sinks_override: list[tuple[str, str]] | None = None,
) -> str:
    """Dynamically resolve the best PipeWire sink for chime playback.

    - When `prefer_epos=True`: prefers any RUNNING or IDLE sink matching
      `1395`, `EPOS`, or `H3PRO`, then any matching SUSPENDED sink, falling
      back to `@DEFAULT_SINK@`.
    - When `prefer_epos=False` (e.g. USB disconnect): returns `@DEFAULT_SINK@`
      directly so a dying/SUSPENDED EPOS sink is never selected.
    """
    if not prefer_epos:
        return "@DEFAULT_SINK@"

    sinks = _query_short_sinks() if sinks_override is None else sinks_override

    for name, state in sinks:
        if is_epos_sink_name(name) and state in ("RUNNING", "IDLE"):
            return name

    for name, _ in sinks:
        if is_epos_sink_name(name):
            return name

    return "@DEFAULT_SINK@"


def wait_for_epos_sink(
    timeout_s: float = 3.0,
    poll_s: float = 0.1,
    settle_s: float = 1.2,
) -> str:
    """Poll PipeWire until the EPOS USB sink appears, then wait for the H3PRO DAC/amp to unmute."""
    deadline = time.monotonic() + timeout_s
    found: str | None = None
    while time.monotonic() < deadline:
        sinks = _query_short_sinks()
        for name, state in sinks:
            if is_epos_sink_name(name) and state in ("RUNNING", "IDLE", "SUSPENDED"):
                found = name
                break
        if found is not None:
            break
        time.sleep(poll_s)

    if found is not None:
        if settle_s > 0:
            time.sleep(settle_s)
        return found
    return "@DEFAULT_SINK@"


def play_tone(
    name: str,
    target_sink: str | None = None,
    prefer_epos: bool | None = None,
    blocking: bool = False,
) -> bool:
    """Play a synthesized EPOS chime via `paplay` (or `pw-play` fallback).

    When `target_sink` is explicitly provided (e.g. `"@DEFAULT_SINK@"` on
    disconnect), it is used verbatim without querying EPOS sinks.
    """
    try:
        wav = ensure_tone_wav(name)
    except (ValueError, OSError):
        return False

    if target_sink is not None:
        sink = target_sink
    else:
        if prefer_epos is None:
            prefer_epos = name != "disconnect"
        sink = resolve_chime_sink(prefer_epos=prefer_epos)

    if shutil.which("paplay"):
        cmd = ["paplay", "--device", sink, str(wav)]
    elif shutil.which("pw-play"):
        cmd = ["pw-play"]
        if sink != "@DEFAULT_SINK@":
            cmd.extend(["--target", sink])
        cmd.append(str(wav))
    else:
        return False

    try:
        if blocking:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False
