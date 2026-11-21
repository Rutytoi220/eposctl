"""Waybar custom module JSON formatter for EPOS H3PRO Hybrid telemetry."""

from __future__ import annotations

from typing import Any

from eposctl.protocol import DeviceTelemetry


def format_waybar_payload(state: DeviceTelemetry) -> dict[str, Any]:
    """Build a Waybar-compatible JSON payload from DeviceTelemetry.

    Conforms to Waybar's custom/script JSON contract:
      {"text", "alt", "tooltip", "class", "percentage"}
    """
    if not state.connected:
        return {
            "text": "H3PRO offline",
            "alt": "disconnected",
            "tooltip": "EPOS H3PRO Hybrid: Not connected",
            "class": "disconnected",
            "percentage": 0,
        }

    pct = state.battery_percent
    pct_str = f"{pct}%" if pct is not None else "--%"

    icons: list[str] = []
    if state.charging:
        icons.append("CHG")
    if state.anc_enabled is True:
        icons.append("ANC")
    if state.mic_muted is True:
        icons.append("MUTE")

    suffix = f" [{' '.join(icons)}]" if icons else ""
    text = f"H3PRO {pct_str}{suffix}"

    # CSS classes for Waybar styling
    classes: list[str] = ["connected", state.connection_mode]
    if state.charging:
        classes.append("charging")
    elif pct is not None:
        if pct <= 15:
            classes.append("critical")
        elif pct <= 30:
            classes.append("warning")
    if state.anc_enabled:
        classes.append("anc-on")
    if state.mic_muted:
        classes.append("mic-muted")
    if state.eq_profile and state.eq_profile != "off":
        classes.append(f"eq-{state.eq_profile}")

    if state.charging:
        alt = "charging"
    elif state.mic_muted:
        alt = "muted"
    elif state.anc_enabled:
        alt = "anc"
    else:
        alt = state.connection_mode

    anc_text = "On" if state.anc_enabled is True else ("Off" if state.anc_enabled is False else "Unknown")
    nf_text = "On" if state.mic_noise_filter is True else ("Off" if state.mic_noise_filter is False else "Unknown")
    chg_text = "Yes" if state.charging is True else ("No" if state.charging is False else "Unknown")
    sleep_text = "On" if state.auto_sleep is True else ("Off" if state.auto_sleep is False else "Unknown")
    sidetone_text = "Off" if state.sidetone_level == 0 else f"{state.sidetone_level}%"
    vp_labels = {"voice": "Voice", "tones": "Tones (SFX)", "off": "Off"}
    vp_text = vp_labels.get(state.voice_prompts or "", "Unknown")
    volt_str = f" ({state.battery_mv / 1000:.2f}V)" if state.battery_mv else ""

    tooltip_lines = [
        f"{state.device_name} ({state.connection_mode})",
        f"Battery: {pct_str}{volt_str} (Charging: {chg_text})",
        f"ANC: {anc_text} | Mic Noise Filter: {nf_text}",
        f"Sidetone: {sidetone_text} | Auto-Sleep: {sleep_text}",
        f"Prompts: {vp_text} | EQ: {state.eq_profile}",
    ]

    return {
        "text": text,
        "alt": alt,
        "tooltip": "\n".join(tooltip_lines),
        "class": " ".join(classes),
        "percentage": pct if pct is not None else 0,
    }
