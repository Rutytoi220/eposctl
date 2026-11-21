#!/usr/bin/env python3
"""Safe, non-destructive 0xEB 0xFE protocol query probe for EPOS H3PRO Hybrid.

Sends ONLY verified read-only 0xEB 0xFE requests on input3 (Usage Page 0xFFFF,
Report ID 0x01, 107B) and prints decoded CRC-8 verified replies.

STRICT SAFETY GUARDRAIL:
  - Never sends Feature reports (0x03 / 0x04 on 0xFF00 are permanently blocked).
  - Defaults to --dry-run unless --send-query is explicitly passed.

Usage:
    uv run python scripts/probe_protocol.py --dry-run
    uv run python scripts/probe_protocol.py --send-query --group 0x12 --cmd 0x03
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from eposctl.constants import PID_H3PRO_DONGLE, REPORT_ID_TELEMETRY_01  # noqa: E402
from eposctl.protocol import (  # noqa: E402
    EPOS_TARGET_DEVICE,
    EPOS_TARGET_HEADSET,
    build_epos_request,
    decode_epos_vendor_frame,
    is_safe_output_report,
)
from eposctl.transport import (  # noqa: E402
    HidDeviceNotFoundError,
    HidPermissionError,
    HidrawTransport,
)


def parse_int(value: str) -> int:
    return int(value, 0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safe, non-destructive 0xEB 0xFE query probe for EPOS H3PRO Hybrid."
    )
    parser.add_argument("--group", type=parse_int, default=0x12, help="16-bit group ID (default: 0x12 battery)")
    parser.add_argument("--cmd", type=parse_int, default=0x03, help="16-bit command ID (default: 0x03 read battery)")
    parser.add_argument(
        "--target",
        type=parse_int,
        default=None,
        help="Target word (default: auto 0x0001 wired / 0x0005 dongle).",
    )
    parser.add_argument("--listen-ms", type=int, default=400, help="Listen timeout in ms (default: 400).")
    parser.add_argument("--send-query", action="store_true", help="Transmit the read query to input3.")
    parser.add_argument("--dry-run", action="store_true", help="Display serialized frame without writing.")
    args = parser.parse_args()

    if not is_safe_output_report("telemetry", REPORT_ID_TELEMETRY_01):
        print("BLOCKED by safety guardrail.", file=sys.stderr)
        return 2

    target = args.target if args.target is not None else EPOS_TARGET_DEVICE
    frame = build_epos_request(args.group, args.cmd, target=target)

    print(f"Interface : input3 (Usage Page 0xFFFF, RID 0x{REPORT_ID_TELEMETRY_01:02X})")
    print(f"Query     : group=0x{args.group:04X}, cmd=0x{args.cmd:04X}, target=0x{target:04X}")
    print(f"Frame Len : {len(frame)} bytes")
    print(f"Frame Hex : {' '.join(f'{b:02X}' for b in frame[:24])} ...")

    if not args.send_query or args.dry_run:
        print("\n[DRY RUN] No bytes written to hardware. Pass --send-query to transmit.")
        return 0

    transport = HidrawTransport(read_only=False)
    try:
        transport.open()
    except (HidDeviceNotFoundError, HidPermissionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        ep = transport.endpoints()
        if args.target is None and ep and ep.product_id == PID_H3PRO_DONGLE:
            target = EPOS_TARGET_HEADSET
            frame = build_epos_request(args.group, args.cmd, target=target)

        written = transport.write_telemetry(frame)
        print(f"\nTX wrote {written} bytes (target=0x{target:04X}). Listening ({args.listen_ms}ms)...")

        deadline = time.monotonic() + (args.listen_ms / 1000.0)
        responses = 0
        while time.monotonic() < deadline:
            rx = transport.read_telemetry(timeout_ms=40)
            if not rx:
                continue
            responses += 1
            vev = decode_epos_vendor_frame(rx)
            if vev:
                print(
                    f"RX [0xEB 0xFE] type=0x{vev.frame_type:04X} target=0x{vev.target:04X} "
                    f"grp=0x{vev.group:04X} cmd=0x{vev.command:04X} values={vev.values} "
                    f"crc_ok={vev.crc_valid} label={vev.label}"
                )
            else:
                print(f"RX RID=0x{rx[0]:02X} ({len(rx)}B): {' '.join(f'{b:02X}' for b in rx[:24])}")

        if responses == 0:
            print("No HID Input response received within listen window.")
    finally:
        transport.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
