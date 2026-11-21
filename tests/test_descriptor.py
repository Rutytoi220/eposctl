"""Unit tests for USB HID Report Descriptor parsing and sysfs discovery."""

from __future__ import annotations

from pathlib import Path

from eposctl.constants import (
    PID_H3PRO_WIRED,
    USAGE_PAGE_CONTROL,
    USAGE_PAGE_TELEMETRY,
    VENDOR_ID,
)
from eposctl.descriptor import (
    discover_hidraw_devices,
    format_descriptor_listing,
    parse_report_descriptor,
)
from eposctl.transport import match_epos_endpoints

# Exact binary descriptors captured from live EPOS H3PRO Hybrid (1395:0101)
INPUT3_RAW_HEX = (
    "06ffff0901a10185010901150026ff007508956a81020902150026ff007508956a9102c0"
    "050c0901a101850415002501750109cd09b109b009b709b509b609b309b4950881068505"
    "09e909ea9502810295068101c0"
)
INPUT4_RAW_HEX = (
    "0600ff0901a101150026ff007508090296410085019102090296410085059102"
    "09029541850281020902950d85068102090295038503b102090295038504b102c0"
)


def test_parse_input3_descriptor() -> None:
    parsed = parse_report_descriptor(bytes.fromhex(INPUT3_RAW_HEX))
    assert len(parsed.raw) == 85
    assert parsed.usage_pages == [0xFFFF, 0x000C]
    assert parsed.primary_usage_page == USAGE_PAGE_TELEMETRY

    by_key = {(r.kind, r.report_id): r for r in parsed.reports}
    assert by_key[("Input", 0x01)].byte_size == 106
    assert by_key[("Input", 0x01)].total_frame_size == 107
    assert by_key[("Output", 0x01)].byte_size == 106
    assert by_key[("Input", 0x04)].byte_size == 1
    assert by_key[("Input", 0x04)].usage_page == 0x000C
    assert by_key[("Input", 0x05)].byte_size == 1
    assert by_key[("Input", 0x05)].usage_page == 0x000C

    listing = format_descriptor_listing(parsed)
    assert "Usage Page (0xFFFF)" in listing
    assert "Usage Page (0x000C)" in listing


def test_parse_input4_descriptor() -> None:
    parsed = parse_report_descriptor(bytes.fromhex(INPUT4_RAW_HEX))
    assert len(parsed.raw) == 65
    assert parsed.usage_pages == [0xFF00]
    assert parsed.primary_usage_page == USAGE_PAGE_CONTROL

    by_key = {(r.kind, r.report_id): r for r in parsed.reports}
    assert by_key[("Output", 0x01)].byte_size == 65
    assert by_key[("Output", 0x05)].byte_size == 65
    assert by_key[("Input", 0x02)].byte_size == 65
    assert by_key[("Input", 0x06)].byte_size == 13
    assert by_key[("Feature", 0x03)].byte_size == 3
    assert by_key[("Feature", 0x04)].byte_size == 3


def test_discover_and_match_endpoints(tmp_path: Path) -> None:
    # Build synthetic /sys/class/hidraw tree
    for name, phys, desc_hex in [
        ("hidraw7", "usb-0000:00:14.0-4.2.2.1/input3", INPUT3_RAW_HEX),
        ("hidraw8", "usb-0000:00:14.0-4.2.2.1/input4", INPUT4_RAW_HEX),
    ]:
        dev_dir = tmp_path / name / "device"
        dev_dir.mkdir(parents=True)
        (dev_dir / "uevent").write_text(
            f"DRIVER=hid-generic\n"
            f"HID_ID=0003:00001395:00000101\n"
            f"HID_NAME=EPOS H3PRO\n"
            f"HID_PHYS={phys}\n"
            f"HID_UNIQ=0123456789ABCDEF\n",
            encoding="utf-8",
        )
        (dev_dir / "report_descriptor").write_bytes(bytes.fromhex(desc_hex))

    devices = discover_hidraw_devices(vendor_id=VENDOR_ID, sysfs_root=tmp_path)
    assert len(devices) == 2

    ep = match_epos_endpoints(devices)
    assert ep is not None
    assert ep.vendor_id == VENDOR_ID
    assert ep.product_id == PID_H3PRO_WIRED
    assert ep.telemetry is not None and ep.telemetry.dev_path == "/dev/hidraw7"
    assert ep.control is not None and ep.control.dev_path == "/dev/hidraw8"
