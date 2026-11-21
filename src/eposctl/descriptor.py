"""USB HID Report Descriptor parser and sysfs hidraw discovery.

Parses raw binary HID report descriptors (per USB HID 1.11 specification)
to extract Usage Pages, Application Collections, and all Input / Output / Feature
Report IDs with their exact bit and byte lengths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class HidReportSpec:
    """Decoded specification for a single HID Report (Input, Output, or Feature)."""

    report_id: int
    kind: str  # "Input", "Output", or "Feature"
    usage_page: int
    bit_size: int
    flags: int

    @property
    def byte_size(self) -> int:
        """Payload length in bytes (excluding the Report ID byte)."""
        return (self.bit_size + 7) // 8

    @property
    def total_frame_size(self) -> int:
        """Total frame size in bytes (including the 1-byte Report ID if non-zero)."""
        return self.byte_size + (1 if self.report_id != 0 else 0)


@dataclass(frozen=True)
class DescriptorItem:
    """A single decoded HID Report Descriptor item."""

    offset: int
    raw: bytes
    item_type: str  # "Main", "Global", "Local", "Reserved"
    tag_name: str
    value: int
    signed_value: int


@dataclass
class ParsedDescriptor:
    """Full parsed result of a HID Report Descriptor."""

    raw: bytes
    items: list[DescriptorItem] = field(default_factory=list)
    usage_pages: list[int] = field(default_factory=list)
    reports: list[HidReportSpec] = field(default_factory=list)

    @property
    def primary_usage_page(self) -> int | None:
        return self.usage_pages[0] if self.usage_pages else None


@dataclass(frozen=True)
class HidrawDeviceInfo:
    """Metadata for a Linux /sys/class/hidraw/hidraw* node."""

    dev_path: str
    sys_path: str
    vendor_id: int
    product_id: int
    name: str
    phys: str
    uniq: str
    driver: str
    descriptor: ParsedDescriptor | None = None

    @property
    def interface_suffix(self) -> str:
        """Return trailing USB interface token from HID_PHYS (e.g. 'input3')."""
        if "/" in self.phys:
            return self.phys.rsplit("/", 1)[-1]
        return ""

    @property
    def primary_usage_page(self) -> int | None:
        return self.descriptor.primary_usage_page if self.descriptor else None


_MAIN_TAGS: dict[int, str] = {
    0x8: "Input",
    0x9: "Output",
    0xA: "Collection",
    0xB: "Feature",
    0xC: "End Collection",
}

_GLOBAL_TAGS: dict[int, str] = {
    0x0: "Usage Page",
    0x1: "Logical Minimum",
    0x2: "Logical Maximum",
    0x3: "Physical Minimum",
    0x4: "Physical Maximum",
    0x5: "Unit Exponent",
    0x6: "Unit",
    0x7: "Report Size",
    0x8: "Report ID",
    0x9: "Report Count",
    0xA: "Push",
    0xB: "Pop",
}

_LOCAL_TAGS: dict[int, str] = {
    0x0: "Usage",
    0x1: "Usage Minimum",
    0x2: "Usage Maximum",
    0x3: "Designator Index",
    0x4: "Designator Minimum",
    0x5: "Designator Maximum",
    0x7: "String Index",
    0x8: "String Minimum",
    0x9: "String Maximum",
    0xA: "Delimiter",
}

_COLLECTION_NAMES: dict[int, str] = {
    0x00: "Physical",
    0x01: "Application",
    0x02: "Logical",
    0x03: "Report",
    0x04: "Named Array",
    0x05: "Usage Switch",
    0x06: "Usage Modifier",
}


def decode_item_flags(flags: int) -> str:
    """Decode Main Input/Output/Feature bitmask flags into human-readable form."""
    parts = [
        "Const" if (flags & 0x01) else "Data",
        "Var" if (flags & 0x02) else "Ary",
        "Rel" if (flags & 0x04) else "Abs",
    ]
    if flags & 0x08:
        parts.append("Wrap")
    if flags & 0x10:
        parts.append("NonLinear")
    if flags & 0x20:
        parts.append("NoPref")
    if flags & 0x40:
        parts.append("NullState")
    if flags & 0x80:
        parts.append("Volatile")
    if flags & 0x100:
        parts.append("BufBytes")
    return ", ".join(parts)


def parse_report_descriptor(data: bytes) -> ParsedDescriptor:
    """Parse a raw USB HID Report Descriptor byte stream."""
    result = ParsedDescriptor(raw=data)
    idx = 0
    length = len(data)

    # Global item state
    usage_page = 0
    report_size = 0
    report_count = 0
    report_id = 0
    global_stack: list[tuple[int, int, int, int]] = []

    # Accumulate bit lengths per (kind, report_id, usage_page)
    report_bits: dict[tuple[str, int], tuple[int, int, int]] = {}
    report_order: list[tuple[str, int]] = []

    while idx < length:
        prefix = data[idx]
        offset = idx

        # Long item format (0xFE)
        if prefix == 0xFE:
            if idx + 2 >= length:
                break
            data_len = data[idx + 1]
            long_tag = data[idx + 2]
            raw_item = data[idx : idx + 3 + data_len]
            result.items.append(
                DescriptorItem(
                    offset=offset,
                    raw=raw_item,
                    item_type="Long",
                    tag_name=f"LongItem(0x{long_tag:02X})",
                    value=data_len,
                    signed_value=data_len,
                )
            )
            idx += 3 + data_len
            continue

        size_code = prefix & 0x03
        data_len = 4 if size_code == 3 else size_code
        item_type_code = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F

        if idx + 1 + data_len > length:
            break

        payload = data[idx + 1 : idx + 1 + data_len]
        raw_item = data[idx : idx + 1 + data_len]
        val = int.from_bytes(payload, "little", signed=False) if data_len else 0
        sval = int.from_bytes(payload, "little", signed=True) if data_len else 0

        if item_type_code == 0:
            item_type = "Main"
            tag_name = _MAIN_TAGS.get(tag, f"Main(0x{tag:X})")
        elif item_type_code == 1:
            item_type = "Global"
            tag_name = _GLOBAL_TAGS.get(tag, f"Global(0x{tag:X})")
        elif item_type_code == 2:
            item_type = "Local"
            tag_name = _LOCAL_TAGS.get(tag, f"Local(0x{tag:X})")
        else:
            item_type = "Reserved"
            tag_name = f"Reserved(0x{tag:X})"

        result.items.append(
            DescriptorItem(
                offset=offset,
                raw=raw_item,
                item_type=item_type,
                tag_name=tag_name,
                value=val,
                signed_value=sval,
            )
        )

        # Update Global state
        if item_type == "Global":
            if tag == 0x0:  # Usage Page
                usage_page = val
                if usage_page not in result.usage_pages:
                    result.usage_pages.append(usage_page)
            elif tag == 0x7:  # Report Size
                report_size = val
            elif tag == 0x8:  # Report ID
                report_id = val
            elif tag == 0x9:  # Report Count
                report_count = val
            elif tag == 0xA:  # Push
                global_stack.append((usage_page, report_size, report_count, report_id))
            elif tag == 0xB and global_stack:  # Pop
                usage_page, report_size, report_count, report_id = global_stack.pop()
        elif item_type == "Main" and tag in (0x8, 0x9, 0xB):
            kind = _MAIN_TAGS[tag]
            bits = report_size * report_count
            key = (kind, report_id)
            if key not in report_bits:
                report_bits[key] = (bits, usage_page, val)
                report_order.append(key)
            else:
                prev_bits, prev_up, prev_flags = report_bits[key]
                report_bits[key] = (prev_bits + bits, prev_up, prev_flags | val)

        idx += 1 + data_len

    for kind, rid in report_order:
        bits, up, flags = report_bits[(kind, rid)]
        result.reports.append(
            HidReportSpec(
                report_id=rid,
                kind=kind,
                usage_page=up,
                bit_size=bits,
                flags=flags,
            )
        )

    return result


def format_descriptor_listing(parsed: ParsedDescriptor) -> str:
    """Format a ParsedDescriptor as an indented human-readable HID descriptor listing."""
    lines: list[str] = []
    indent = 0
    for item in parsed.items:
        if item.item_type == "Main" and item.tag_name == "End Collection":
            indent = max(0, indent - 1)

        hex_bytes = " ".join(f"{b:02X}" for b in item.raw)
        prefix = "  " * indent

        if item.tag_name == "Collection":
            cname = _COLLECTION_NAMES.get(item.value, f"0x{item.value:02X}")
            detail = f"{item.tag_name} ({cname})"
        elif item.tag_name in ("Input", "Output", "Feature"):
            detail = f"{item.tag_name} ({decode_item_flags(item.value)})"
        elif item.tag_name in ("Usage Page", "Usage", "Usage Minimum", "Usage Maximum"):
            detail = f"{item.tag_name} (0x{item.value:04X})"
        elif item.tag_name == "Report ID":
            detail = f"{item.tag_name} (0x{item.value:02X})"
        elif item.tag_name == "End Collection":
            detail = "End Collection"
        elif item.tag_name in ("Logical Minimum", "Logical Maximum", "Physical Minimum", "Physical Maximum"):
            detail = f"{item.tag_name} ({item.signed_value} / 0x{item.value:X})"
        else:
            detail = f"{item.tag_name} ({item.value})"

        lines.append(f"0x{item.offset:04X}: {hex_bytes:<14} {prefix}{detail}")

        if item.item_type == "Main" and item.tag_name == "Collection":
            indent += 1

    return "\n".join(lines)


def parse_uevent(text: str) -> dict[str, str]:
    """Parse a Linux sysfs uevent file into a key-value dict."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_hid_id(hid_id: str) -> tuple[int, int, int] | None:
    """Parse HID_ID='0003:00001395:00000101' into (bus, vid, pid)."""
    parts = hid_id.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0], 16), int(parts[1], 16), int(parts[2], 16)
    except ValueError:
        return None


def discover_hidraw_devices(
    vendor_id: int | None = None,
    product_ids: Iterable[int] | None = None,
    sysfs_root: Path = Path("/sys/class/hidraw"),
) -> list[HidrawDeviceInfo]:
    """Discover hidraw nodes from sysfs and parse their report descriptors."""
    pid_set = set(product_ids) if product_ids is not None else None
    devices: list[HidrawDeviceInfo] = []

    if not sysfs_root.exists():
        return devices

    for entry in sorted(sysfs_root.glob("hidraw*"), key=lambda p: p.name):
        uevent_path = entry / "device" / "uevent"
        if not uevent_path.exists():
            continue
        try:
            uevent = parse_uevent(uevent_path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue

        parsed_id = parse_hid_id(uevent.get("HID_ID", ""))
        if not parsed_id:
            continue
        _, vid, pid = parsed_id

        if vendor_id is not None and vid != vendor_id:
            continue
        if pid_set is not None and pid not in pid_set:
            continue

        desc_path = entry / "device" / "report_descriptor"
        parsed_desc: ParsedDescriptor | None = None
        if desc_path.exists():
            try:
                raw_desc = desc_path.read_bytes()
                parsed_desc = parse_report_descriptor(raw_desc)
            except OSError:
                parsed_desc = None

        devices.append(
            HidrawDeviceInfo(
                dev_path=f"/dev/{entry.name}",
                sys_path=str(entry),
                vendor_id=vid,
                product_id=pid,
                name=uevent.get("HID_NAME", ""),
                phys=uevent.get("HID_PHYS", ""),
                uniq=uevent.get("HID_UNIQ", ""),
                driver=uevent.get("DRIVER", ""),
                descriptor=parsed_desc,
            )
        )

    return devices
