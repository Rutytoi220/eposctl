# Capturing EPOS Gaming Suite HID Traffic with `usbmon` & Wireshark

If you want to capture the exact byte-for-byte frames sent by **EPOS Gaming Suite** (running in a Windows VM with USB passthrough) for sidetone, auto-sleep timer, voice prompts, or ANC readback, use Linux's built-in `usbmon` kernel module on the host.

---

## 1. Prerequisites (Arch Linux Host)

```bash
sudo pacman -S wireshark-qt tcpdump usbutils
sudo usermod -aG wireshark "$USER"
# Log out and back in (or run `newgrp wireshark`)
```

## 2. Identify the USB Bus & Device Number

```bash
lsusb -d 1395:
# Example:
# Bus 003 Device 020: ID 1395:0101 DSEA A/S EPOS H3PRO
```

Note the bus number (e.g. `3` -> `usbmon3`) and device address (`20`).

## 3. Load `usbmon` & Capture

```bash
sudo modprobe usbmon
sudo chmod 640 /dev/usbmon3
sudo chgrp wireshark /dev/usbmon3
```

Start a headless capture to a `.pcapng` file (or open `usbmon3` directly in Wireshark):

```bash
tshark -i usbmon3 -w epos-h3pro-capture.pcapng
```

## 4. Perform Controlled Single-Variable Actions in the Windows VM

Pass the `1395:0101` (or `1395:0303`) USB device into the Windows VM running EPOS Gaming Suite, wait 5 seconds between each action, and log timestamps:

1. **Idle baseline** (10 seconds) — observe any periodic battery/status polls.
2. **Sidetone:** set `0%` -> `25%` -> `50%` -> `100%` -> `0%`.
3. **Auto-Sleep Timer:** set `Off` -> `5 min` -> `15 min` -> `30 min` -> `60 min`.
4. **Voice Prompts:** toggle `OFF` -> `ON`.
5. **Physical switches:** toggle ANC slider ON/OFF, raise/lower mic boom arm.

Stop `tshark` with `Ctrl+C`.

## 5. Filter & Inspect in Wireshark

Use this display filter to isolate ONLY HID Interrupt/Control transfers for your device (replace `20` with your device address):

```text
usb.bus_id == 3 && usb.device_address == 20 && (usb.transfer_type == 0x01 || usb.transfer_type == 0x02) && usb.data_len > 0
```

Focus on:
- **`HID Data` (`usbhid.data`)** for Interrupt OUT (`input3` EP / `input4` EP) and Interrupt IN responses.
- **`SET_REPORT` / `GET_REPORT`** Control transfers (`usb.bmRequestType == 0x21` or `0xa1`).

Export filtered packet bytes to JSON for diffing:

```bash
tshark -r epos-h3pro-capture.pcapng \
  -Y "usb.device_address == 20 && usb.data_len > 0" \
  -T fields -e frame.time_relative -e usb.endpoint_address -e usb.capdata \
  > captures/epos-h3pro-frames.tsv
```

Once confirmed, update the command opcode constants in `src/eposctl/protocol.py` and document the verified frames in `docs/PROTOCOL.md`.
