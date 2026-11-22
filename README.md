# eposctl

A Linux CLI, TUI, and Waybar widget for the **EPOS H3PRO Hybrid** headset (wired and GSA 70 dongle).

Lets you check battery/charging/ANC/mic status, tweak sidetone, auto-sleep, and voice prompts, and switch PipeWire EQ presets without needing the Windows software.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Rutytoi220/eposctl/main/install.sh | bash
```

Or with `uv` / `pipx`:

```bash
uv tool install git+https://github.com/Rutytoi220/eposctl
```

For non-root access to the headset, copy the udev rule and reload:

```bash
sudo cp udev/70-epos-h3pro.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=hidraw
```

## Usage

```bash
eposctl tui               # interactive TUI
eposctl status            # battery, ANC, mic, connection info
eposctl status --json     # Waybar JSON output
eposctl sidetone 40       # 0-100 or off
eposctl sleep 15          # off | 5 | 15 | 30 | 60
eposctl voice-prompts off # on | off
eposctl eq esports        # flat | esports | music | movie | off
```

### Waybar snippet

```jsonc
"custom/epos": {
    "exec": "eposctl status --json",
    "return-type": "json",
    "interval": 5,
    "format": "{}",
    "on-click": "eposctl eq esports",
    "on-click-right": "eposctl eq off"
}
```

## License

MIT
