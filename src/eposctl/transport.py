"""HID transport abstractions for EPOS H3PRO Hybrid.

Dynamically discovers EPOS hidraw nodes by VID/PID and HID Usage Page
(0xFFFF for telemetry/input3, 0xFF00 for control/input4) — never hardcoding
/dev/hidrawN paths.

Supports:
  1. Direct non-blocking Linux hidraw I/O (zero external C-extension deps)
  2. Optional libhidapi-hidraw.so.0 via ctypes when preferred
  3. MockHidTransport for deterministic unit tests and offline previews
"""

from __future__ import annotations

import errno
import os
import select
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass

from eposctl.constants import (
    INTERFACE_CONTROL,
    INTERFACE_TELEMETRY,
    PID_H3PRO_WIRED,
    SUPPORTED_PIDS,
    USAGE_PAGE_CONTROL,
    USAGE_PAGE_TELEMETRY,
    VENDOR_ID,
)
from eposctl.descriptor import HidrawDeviceInfo, discover_hidraw_devices


class HidTransportError(RuntimeError):
    """Base error for HID transport failures."""


class HidDeviceNotFoundError(HidTransportError):
    """Raised when no supported EPOS H3PRO Hybrid HID device is connected."""


class HidPermissionError(HidTransportError):
    """Raised when the user lacks read/write permissions on /dev/hidraw*."""


@dataclass(frozen=True)
class MatchedEndpoints:
    """Resolved telemetry (0xFFFF) and control (0xFF00) hidraw endpoints."""

    vendor_id: int
    product_id: int
    product_name: str
    telemetry: HidrawDeviceInfo | None
    control: HidrawDeviceInfo | None


def match_epos_endpoints(
    devices: list[HidrawDeviceInfo] | None = None,
) -> MatchedEndpoints | None:
    """Match EPOS H3PRO telemetry (0xFFFF / input3) and control (0xFF00 / input4) nodes."""
    if devices is None:
        devices = discover_hidraw_devices(
            vendor_id=VENDOR_ID,
            product_ids=SUPPORTED_PIDS.keys(),
        )
    if not devices:
        return None

    telemetry: HidrawDeviceInfo | None = None
    control: HidrawDeviceInfo | None = None

    # Primary match: HID Usage Page from parsed report descriptor
    for dev in devices:
        if dev.primary_usage_page == USAGE_PAGE_TELEMETRY and telemetry is None:
            telemetry = dev
        elif dev.primary_usage_page == USAGE_PAGE_CONTROL and control is None:
            control = dev

    # Fallback match: USB interface suffix in HID_PHYS
    for dev in devices:
        if telemetry is None and dev.interface_suffix == INTERFACE_TELEMETRY:
            telemetry = dev
        elif control is None and dev.interface_suffix == INTERFACE_CONTROL:
            control = dev

    ref = telemetry or control or devices[0]
    return MatchedEndpoints(
        vendor_id=ref.vendor_id,
        product_id=ref.product_id,
        product_name=SUPPORTED_PIDS.get(ref.product_id, ref.name or "EPOS H3PRO"),
        telemetry=telemetry,
        control=control,
    )


class HidTransport(ABC):
    """Abstract bidirectional HID transport for telemetry (0xFFFF) and control (0xFF00)."""

    @abstractmethod
    def open(self) -> None:
        """Open the underlying HID endpoints."""

    @abstractmethod
    def close(self) -> None:
        """Close any open HID handles."""

    @abstractmethod
    def is_open(self) -> bool:
        """Return True if at least one HID endpoint is open."""

    @abstractmethod
    def endpoints(self) -> MatchedEndpoints | None:
        """Return discovered endpoint metadata."""

    @abstractmethod
    def read_telemetry(self, timeout_ms: int = 100, size: int = 128) -> bytes | None:
        """Read a single HID Input report from the telemetry interface (0xFFFF)."""

    @abstractmethod
    def write_telemetry(self, data: bytes) -> int:
        """Write a HID Output report to the telemetry interface (0xFFFF)."""

    @abstractmethod
    def read_control(self, timeout_ms: int = 100, size: int = 128) -> bytes | None:
        """Read a single HID Input report from the control interface (0xFF00)."""

    @abstractmethod
    def write_control(self, data: bytes) -> int:
        """Write a HID Output report to the control interface (0xFF00)."""

    def __enter__(self) -> HidTransport:
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class HidrawTransport(HidTransport):
    """Linux hidraw non-blocking transport matching EPOS devices dynamically via sysfs."""

    def __init__(self, read_only: bool = False) -> None:
        self._read_only = read_only
        self._endpoints: MatchedEndpoints | None = None
        self._telemetry_fd: int | None = None
        self._control_fd: int | None = None

    def endpoints(self) -> MatchedEndpoints | None:
        if self._endpoints is None:
            self._endpoints = match_epos_endpoints()
        return self._endpoints

    def _open_node(self, dev: HidrawDeviceInfo | None) -> int | None:
        if dev is None:
            return None
        flags = (os.O_RDONLY if self._read_only else os.O_RDWR) | os.O_NONBLOCK
        try:
            return os.open(dev.dev_path, flags)
        except PermissionError as exc:
            raise HidPermissionError(
                f"Permission denied opening {dev.dev_path} ({dev.interface_suffix}). "
                "Install udev/70-epos-h3pro.rules (prefix < 73 so systemd uaccess applies) and reload udev:\n"
                "  sudo cp udev/70-epos-h3pro.rules /etc/udev/rules.d/\n"
                "  sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=hidraw"
            ) from exc
        except OSError as exc:
            raise HidTransportError(f"Failed to open {dev.dev_path}: {exc}") from exc

    def open(self) -> None:
        ep = match_epos_endpoints()
        if ep is None:
            raise HidDeviceNotFoundError(
                "EPOS H3PRO Hybrid (VID 0x1395, PID 0x0101 or 0x0303) not found."
            )
        self._endpoints = ep
        try:
            self._telemetry_fd = self._open_node(ep.telemetry)
            self._control_fd = self._open_node(ep.control)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        for attr in ("_telemetry_fd", "_control_fd"):
            fd = getattr(self, attr)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
                setattr(self, attr, None)

    def is_open(self) -> bool:
        return self._telemetry_fd is not None or self._control_fd is not None

    @staticmethod
    def _read_fd(fd: int | None, timeout_ms: int, size: int) -> bytes | None:
        if fd is None:
            return None
        timeout = max(0.0, timeout_ms / 1000.0)
        readable, _, _ = select.select([fd], [], [], timeout)
        if not readable:
            return None
        try:
            data = os.read(fd, size)
            return data if data else None
        except BlockingIOError:
            return None
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return None
            raise HidTransportError(f"HID read error: {exc}") from exc

    @staticmethod
    def _write_fd(fd: int | None, data: bytes, name: str) -> int:
        if fd is None:
            raise HidTransportError(f"HID {name} endpoint is not open.")
        try:
            return os.write(fd, data)
        except OSError as exc:
            raise HidTransportError(f"HID write error on {name}: {exc}") from exc

    def read_telemetry(self, timeout_ms: int = 100, size: int = 128) -> bytes | None:
        return self._read_fd(self._telemetry_fd, timeout_ms, size)

    def write_telemetry(self, data: bytes) -> int:
        return self._write_fd(self._telemetry_fd, data, "telemetry (0xFFFF)")

    def read_control(self, timeout_ms: int = 100, size: int = 128) -> bytes | None:
        return self._read_fd(self._control_fd, timeout_ms, size)

    def write_control(self, data: bytes) -> int:
        return self._write_fd(self._control_fd, data, "control (0xFF00)")


class MockHidTransport(HidTransport):
    """In-memory mock HID transport for tests and offline CLI/TUI demonstrations."""

    def __init__(
        self,
        product_id: int = PID_H3PRO_WIRED,
        telemetry_rx: list[bytes] | None = None,
        control_rx: list[bytes] | None = None,
        auto_reply: bool = False,
    ) -> None:
        self._opened = False
        self._product_id = product_id
        self._auto_reply = auto_reply
        self.telemetry_rx: deque[bytes] = deque(telemetry_rx or [])
        self.control_rx: deque[bytes] = deque(control_rx or [])
        self.telemetry_tx: list[bytes] = []
        self.control_tx: list[bytes] = []
        self._mock_state: dict[tuple[int, int], tuple[int, ...]] = {
            (0x12, 0x03): (100,),      # Battery 100%
            (0x12, 0x01): (4158, 5),   # 4158 mV, level 5
            (0x17, 0x04): (0,),        # ANC OFF
            (0x07, 0x05): (2,),        # Tones (SFX only)
            (0x0A, 0x0C): (89,),       # Sidetone ~35%
            (0x0A, 0x12): (1,),        # Mic noise filter ON
            (0x01, 0x20): (1,),        # Auto-sleep ON
            (0x01, 0x09): (1,),        # Dongle connected
            (0x01, 0x03): (1, 3, 5),   # Firmware v1.3.5
        }

        self._endpoints = MatchedEndpoints(
            vendor_id=VENDOR_ID,
            product_id=product_id,
            product_name=SUPPORTED_PIDS.get(product_id, "EPOS H3PRO Hybrid (Mock)"),
            telemetry=HidrawDeviceInfo(
                dev_path="/dev/hidraw-mock-telemetry",
                sys_path="/sys/class/hidraw/hidraw-mock-telemetry",
                vendor_id=VENDOR_ID,
                product_id=product_id,
                name="EPOS H3PRO",
                phys="usb-mock/input3",
                uniq="MOCK0123456789",
                driver="hid-generic",
            ),
            control=HidrawDeviceInfo(
                dev_path="/dev/hidraw-mock-control",
                sys_path="/sys/class/hidraw/hidraw-mock-control",
                vendor_id=VENDOR_ID,
                product_id=product_id,
                name="EPOS H3PRO",
                phys="usb-mock/input4",
                uniq="MOCK0123456789",
                driver="hid-generic",
            ),
        )

    def open(self) -> None:
        self._opened = True

    def close(self) -> None:
        self._opened = False

    def is_open(self) -> bool:
        return self._opened

    def endpoints(self) -> MatchedEndpoints | None:
        return self._endpoints

    def read_telemetry(self, timeout_ms: int = 100, size: int = 128) -> bytes | None:
        if not self._opened or not self.telemetry_rx:
            return None
        return self.telemetry_rx.popleft()[:size]

    def write_telemetry(self, data: bytes) -> int:
        if not self._opened:
            raise HidTransportError("MockHidTransport is not open.")
        self.telemetry_tx.append(bytes(data))
        if self._auto_reply and len(data) >= 17 and data[1:3] == b"\xEB\xFE":
            import struct
            from eposctl.protocol import build_mock_reply_frame

            _, _, _, _, target, plen, _ = struct.unpack_from("<B2sHHHHH", data, 0)
            words = struct.unpack_from("<" + "H" * (plen // 2), data, 13)
            grp, cmd = words[0], words[1]
            reply_tgt = max(0, target - 1)
            if (grp, cmd) == (0x0A, 0x0B) and len(words) >= 3:
                self._mock_state[(0x0A, 0x0C)] = (words[2],)
                self.telemetry_rx.append(build_mock_reply_frame(grp, cmd, (0,), target=reply_tgt))
            elif (grp, cmd) == (0x0A, 0x11) and len(words) >= 3:
                self._mock_state[(0x0A, 0x12)] = (words[2],)
                self.telemetry_rx.append(build_mock_reply_frame(grp, cmd, (0,), target=reply_tgt))
            elif (grp, cmd) == (0x01, 0x1F) and len(words) >= 3:
                self._mock_state[(0x01, 0x20)] = (words[2],)
                self.telemetry_rx.append(build_mock_reply_frame(grp, cmd, (0,), target=reply_tgt))
            elif (grp, cmd) == (0x07, 0x01) and len(words) >= 3:
                self._mock_state[(0x07, 0x05)] = (words[2],)
                self.telemetry_rx.append(build_mock_reply_frame(grp, cmd, (0,), target=reply_tgt))
            elif (grp, cmd) in self._mock_state:
                self.telemetry_rx.append(
                    build_mock_reply_frame(grp, cmd, self._mock_state[(grp, cmd)], target=reply_tgt)
                )
        return len(data)

    def read_control(self, timeout_ms: int = 100, size: int = 128) -> bytes | None:
        if not self._opened or not self.control_rx:
            return None
        return self.control_rx.popleft()[:size]

    def write_control(self, data: bytes) -> int:
        if not self._opened:
            raise HidTransportError("MockHidTransport is not open.")
        self.control_tx.append(bytes(data))
        return len(data)
