#!/usr/bin/env python3
"""Passive non-blocking HID event sniffer for EPOS H3PRO Hybrid.

Opens the dynamically matched telemetry node (Usage Page 0xFFFF / input3) — and
optionally the control input node (Usage Page 0xFF00 / input4) — in read-only
non-blocking mode, printing timestamped hex dumps, byte-level diffs against the
previous frame of the same Report ID, and decoded Consumer Control events.

Usage:
    uv run python scripts/sniff_events.py
    uv run python scripts/sniff_events.py --both --duration 30
    uv run python scripts/sniff_events.py --log captures/session.jsonl
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eposctl.protocol import decode_consumer_report, decode_epos_vendor_frame  # noqa: E402
from eposctl.transport import (  # noqa: E402
    HidDeviceNotFoundError,
    HidPermissionError,
    HidrawTransport,
)


def format_byte_diff(prev: bytes | None, curr: bytes) -> str:
    """Return a concise summary of byte offsets that changed since the previous frame."""
    if prev is None:
        return "(initial frame)"
    diffs: list[str] = []
    max_len = max(len(prev), len(curr))
    for i in range(max_len):
        old_b = prev[i] if i < len(prev) else None
        new_b = curr[i] if i < len(curr) else None
        if old_b != new_b:
            old_s = f"{old_b:02X}" if old_b is not None else "--"
            new_s = f"{new_b:02X}" if new_b is not None else "--"
            diffs.append(f"[{i}]:{old_s}->{new_s}")
    return " ".join(diffs) if diffs else "(identical)"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Passive non-blocking HID sniffer for EPOS H3PRO Hybrid."
    )
    parser.add_argument(
        "--both",
        action="store_true",
        help="Also listen for Input reports on input4 (Usage Page 0xFF00).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Stop automatically after N seconds (0 = run until Ctrl+C).",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Optional JSONL file to record captured frames.",
    )
    args = parser.parse_args()

    stop = False

    def _handle_sigint(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_sigint)
    signal.signal(signal.SIGTERM, _handle_sigint)

    transport = HidrawTransport(read_only=True)
    try:
        transport.open()
    except (HidDeviceNotFoundError, HidPermissionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    ep = transport.endpoints()
    assert ep is not None
    print(f"Connected: {ep.product_name} (VID=0x{ep.vendor_id:04X}, PID=0x{ep.product_id:04X})")
    if ep.telemetry:
        print(f"  Telemetry (0xFFFF): {ep.telemetry.dev_path} ({ep.telemetry.interface_suffix})")
    if args.both and ep.control:
        print(f"  Control   (0xFF00): {ep.control.dev_path} ({ep.control.interface_suffix})")
    print("Listening for HID events (toggle ANC, mic boom, volume wheel, BT button)... Ctrl+C to stop.\n")

    last_frames: dict[tuple[str, int], bytes] = {}
    start = time.monotonic()
    count = 0
    log_fp = None

    try:
        if args.log:
            args.log.parent.mkdir(parents=True, exist_ok=True)
            log_fp = args.log.open("a", encoding="utf-8")

        while not stop:
            if args.duration > 0 and (time.monotonic() - start) >= args.duration:
                break

            sources: list[tuple[str, bytes | None]] = [
                ("input3/0xFFFF", transport.read_telemetry(timeout_ms=50))
            ]
            if args.both:
                sources.append(("input4/0xFF00", transport.read_control(timeout_ms=20)))

            for iface, frame in sources:
                if not frame:
                    continue
                count += 1
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
                rid = frame[0]
                key = (iface, rid)
                diff_str = format_byte_diff(last_frames.get(key), frame)
                last_frames[key] = frame

                hex_str = " ".join(f"{b:02X}" for b in frame)
                decoded = ""
                if iface.startswith("input3"):
                    ev = decode_consumer_report(frame)
                    if ev is not None:
                        decoded = f"  [Consumer: {', '.join(ev.events) or 'released'}]"
                    else:
                        vev = decode_epos_vendor_frame(frame)
                        if vev is not None:
                            tag = vev.label or f"feat=0x{vev.feature_id:04X} prop=0x{vev.property_id:04X}"
                            decoded = f"  [EPOS: {tag} val=0x{vev.value:04X}]"

                print(f"[{ts}] {iface} RID=0x{rid:02X} ({len(frame):3d}B) | diff: {diff_str}{decoded}")
                print(f"           hex: {hex_str}")

                if log_fp:
                    log_fp.write(
                        json.dumps(
                            {
                                "ts": datetime.now(timezone.utc).isoformat(),
                                "interface": iface,
                                "report_id": rid,
                                "length": len(frame),
                                "hex": frame.hex(),
                                "diff": diff_str,
                            }
                        )
                        + "\n"
                    )
                    log_fp.flush()
    finally:
        if log_fp:
            log_fp.close()
        transport.close()

    print(f"\nCaptured {count} HID frame(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
