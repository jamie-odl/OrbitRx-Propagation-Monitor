"""Optional OmniRig / CAT control bridge for Windows radios."""

from __future__ import annotations

from orbitrx.spots.models import CatControlSettings


def tune_frequency_hz(frequency_hz: float, settings: CatControlSettings) -> tuple[bool, str]:
    if not settings.enabled:
        return False, "CAT control disabled"

    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except Exception:
        return False, "pywin32 is not installed"

    rig_index = 1 if settings.rig_number != 2 else 2
    try:
        pythoncom.CoInitialize()
        omnirig = win32com.client.Dispatch("OmniRig.OmniRigX")
        rig = omnirig.Rig1 if rig_index == 1 else omnirig.Rig2
        rig.Freq = int(round(frequency_hz))
        return True, f"Rig{rig_index} tuned to {frequency_hz / 1_000_000.0:.6f} MHz"
    except Exception as exc:
        return False, f"OmniRig error: {exc}"