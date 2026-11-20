from __future__ import annotations

import datetime
import sys
from typing import Callable

from orbitrx.config import AppConfig
from orbitrx.paths import user_data_path
from orbitrx.utils import normalize_freq_mhz

try:
    import serial
    CAT_AVAILABLE = True
except ImportError:
    serial = None
    CAT_AVAILABLE = False

CAT_LOG_NAME = "cat_log.txt"  # under paths.user_data_dir()


def _kenwood_cmd(freq_hz: int) -> bytes:
    return f"FA{freq_hz:011d};".encode("ascii")


def _icom_cmd(freq_hz: int) -> bytes:
    # CI-V set freq VFO A — simplified; many Icom rigs accept Kenwood-style via emulation
    return _kenwood_cmd(freq_hz)


def _yaesu_cmd(freq_hz: int) -> bytes:
    return f"FA{freq_hz:08d};".encode("ascii")


RIG_BACKENDS = ("serial", "omnirig")

RIG_PROFILES = {
    "kenwood": _kenwood_cmd,
    "icom": _icom_cmd,
    "yaesu": _yaesu_cmd,
}

# Shown in Settings. The stored config value stays the dict key.
RIG_PROFILE_LABELS = {
    "kenwood": "Kenwood",
    "icom": "Icom",
    "yaesu": "Yaesu",
}

# Read-only queries. None of these set a frequency.
_KENWOOD_READ_FA = b"FA;"
_YAESU_READ_FA = b"FA;"
# CI-V read operating frequency, addressed to 0x00 (the rig), from controller 0xE0.
_ICOM_READ_FREQ = bytes([0xFE, 0xFE, 0x00, 0xE0, 0x03, 0xFD])


def read_query_for_profile(profile: str) -> bytes | None:
    """Bytes to ask the rig for its frequency. None when this profile has no read-back."""
    key = str(profile or "").lower()
    if key == "kenwood":
        return _KENWOOD_READ_FA
    if key == "yaesu":
        return _YAESU_READ_FA
    if key == "icom":
        return _ICOM_READ_FREQ
    return None


def _bcd_frequency_hz(payload: bytes) -> int | None:
    """Five CI-V BCD bytes, least-significant digit first, into Hz."""
    if len(payload) < 5:
        return None
    value = 0
    mul = 1
    for byte in payload[:5]:
        lo = byte & 0x0F
        hi = (byte >> 4) & 0x0F
        if lo > 9 or hi > 9:
            return None
        value += lo * mul
        mul *= 10
        value += hi * mul
        mul *= 10
    return value


def _parse_civ_frequency(buf: bytes) -> float | None:
    """Return MHz from the first CI-V operating-frequency frame in buf, else None."""
    start = 0
    while True:
        i = buf.find(b"\xfe\xfe", start)
        if i < 0 or i + 6 >= len(buf):
            return None
        end = buf.find(b"\xfd", i + 4)
        if end < 0:
            return None
        frame = buf[i + 2:end]
        # to, from, command, then BCD payload
        if len(frame) >= 3 and frame[2] == 0x03:
            hz = _bcd_frequency_hz(frame[3:])
            if hz is not None and hz > 0:
                return hz / 1_000_000.0
        start = i + 2


def _parse_fa_mhz(buf: bytes, widths: tuple[int, ...]) -> float | None:
    """Kenwood/Yaesu `FA<digits>;` reply. widths is the accepted digit counts."""
    text = buf.decode("ascii", errors="ignore").upper()
    for marker in ("FA",):
        pos = text.rfind(marker)
        while pos >= 0:
            end = text.find(";", pos)
            if end > pos:
                digits = text[pos + 2:end]
                if digits.isdigit() and len(digits) in widths:
                    return int(digits) / 1_000_000.0
            pos = text.rfind(marker, 0, pos)
    return None


def classify_cat_reply(profile: str, buf: bytes) -> tuple[str, str]:
    """Turn bytes read from the rig into (status, detail).

    status is ok, wrong_baud, or timeout. detail is a short human message.
    An empty buffer is no reply (timeout). Non-empty bytes that are not a
    frequency frame are a wrong-baud / no-valid-reply result.
    """
    if not buf:
        return "timeout", "Timed out waiting for the rig"
    key = str(profile or "").lower()
    mhz: float | None = None
    if key == "icom":
        mhz = _parse_civ_frequency(buf)
        if mhz is None:
            # Kenwood-emulation Icom rigs answer FA; even though we asked in CI-V.
            mhz = _parse_fa_mhz(buf, (8, 9, 11))
    elif key == "yaesu":
        mhz = _parse_fa_mhz(buf, (8, 9))
    else:
        mhz = _parse_fa_mhz(buf, (11,))
    if mhz is None or mhz <= 0:
        return "wrong_baud", "No valid reply"
    return "ok", f"Read {mhz:.6f} MHz"


def _port_is_busy(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    text = str(exc).lower()
    if "access is denied" in text or "permission" in text or "resource busy" in text:
        return True
    errno = getattr(exc, "errno", None)
    winerror = getattr(exc, "winerror", None)
    return errno in (13, 16) or winerror == 5


def _read_omnirig_hz(rig_number: int) -> float:
    """Read Rig.Freq in Hz. Raises ImportError without pywin32, AttributeError
    when the rig object has no frequency to read. Does not assign Freq."""
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except Exception as exc:
        raise ImportError("pywin32 is not installed") from exc
    index = 2 if int(rig_number or 1) == 2 else 1
    pythoncom.CoInitialize()
    omnirig = win32com.client.Dispatch("OmniRig.OmniRigX")
    rig = omnirig.Rig1 if index == 1 else omnirig.Rig2
    try:
        freq = rig.Freq
    except AttributeError:
        raise
    except Exception as exc:
        text = str(exc).lower()
        if "freq" in text and ("not " in text or "attribute" in text or "unknown" in text):
            raise AttributeError(str(exc)) from exc
        raise
    if isinstance(freq, bool) or not isinstance(freq, (int, float)) or freq <= 0:
        raise AttributeError("Freq is not supported")
    return float(freq)


def format_probe_result(status: str, message: str) -> str:
    """Single string the Settings UI splits on the first newline."""
    return f"{status}\n{message}"


def parse_probe_result(result: str) -> tuple[str, str]:
    status, _, message = str(result).partition("\n")
    known = {"ok", "timeout", "wrong_baud", "busy", "unavailable", "unverified", "error"}
    if status not in known:
        return "error", str(result)
    return status, message or status


def default_port_fallback() -> str:
    """Platform-appropriate placeholder when no serial ports are detected."""
    return "COM3" if sys.platform.startswith("win") else "/dev/ttyUSB0"


class CatController:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self._ser = None

    def backend(self) -> str:
        value = str(self.cfg.get("rig_control", "serial") or "serial").lower()
        return value if value in RIG_BACKENDS else "serial"

    def _tune_omnirig(self, freq_val: float) -> str:
        from orbitrx.spots.models import CatControlSettings
        from orbitrx.spots.omnirig import tune_frequency_hz

        settings = CatControlSettings(enabled=True, rig_number=int(self.cfg.get("omnirig_rig_number", 1) or 1))
        ok, msg = tune_frequency_hz(freq_val * 1_000_000, settings)
        self._log(f"OMNIRIG {'OK' if ok else 'FAIL'} {freq_val} {msg}")
        return msg

    def list_ports(self) -> list[str]:
        return [device for device, _ in self.list_ports_detailed()]

    def list_ports_detailed(self) -> list[tuple[str, str]]:
        """(device, description) pairs, e.g. ("COM3", "USB Serial Port"). Never surfaces
        a non-Windows device path when running on Windows (pyserial only reports real
        COM ports there, but this guards the fallback/display path too)."""
        if not CAT_AVAILABLE:
            return []
        try:
            from serial.tools import list_ports
            ports = [(p.device, p.description or p.device) for p in list_ports.comports()]
        except Exception:
            return []
        if sys.platform.startswith("win"):
            ports = [(d, desc) for d, desc in ports if d.upper().startswith("COM")]
        return ports

    def _log(self, msg: str) -> None:
        with open(user_data_path(CAT_LOG_NAME), "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now(datetime.timezone.utc).isoformat()} {msg}\n")

    def connect(self) -> bool:
        if not CAT_AVAILABLE:
            return False
        try:
            if self._ser and self._ser.is_open:
                return True
            self._ser = serial.Serial(
                self.cfg.get("cat_port", "COM3"),
                int(self.cfg.get("cat_baud", 9600)),
                timeout=float(self.cfg.get("cat_timeout", 0.5)),
            )
            self._log(f"CONNECTED {self.cfg.get('cat_port')}")
            return True
        except Exception as e:
            self._log(f"CONNECT_FAIL {e}")
            return False

    def disconnect(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
            self._log("DISCONNECTED")

    def probe(
        self,
        *,
        port: str,
        baud: int,
        profile: str,
        backend: str,
        timeout: float = 4.0,
        rig_number: int = 1,
    ) -> str:
        """Ask the radio for its frequency and report whether it answered.

        Does not retune, and does not write port, baud, or profile into cfg.
        Returns format_probe_result(status, message).
        """
        backend_name = str(backend or "serial").lower()
        if backend_name not in RIG_BACKENDS:
            backend_name = "serial"
        if backend_name == "omnirig":
            return self._probe_omnirig(rig_number)
        if not CAT_AVAILABLE or serial is None:
            return format_probe_result("unavailable", "pyserial not installed")
        query = read_query_for_profile(profile)
        if query is None:
            return format_probe_result("unverified", "sent, not verified")
        device = (port or "").strip()
        if not device:
            return format_probe_result("error", "Enter a port like COM3.")
        # Drop our own handle first so the probe open is not blocked by it.
        self._release_own_port()
        ser = None
        try:
            ser = serial.Serial(device, int(baud), timeout=max(0.2, float(timeout)))
            ser.write(query)
            buf = ser.read(256)
            status, detail = classify_cat_reply(profile, buf)
            if status == "wrong_baud":
                detail = f"No valid reply at {int(baud)} baud"
            self._log(f"PROBE {status} port={device} baud={baud} profile={profile} bytes={buf!r}")
            return format_probe_result(status, detail)
        except Exception as exc:
            self._log(f"PROBE_FAIL {exc}")
            if _port_is_busy(exc):
                return format_probe_result("busy", f"{device} is in use by another program")
            return format_probe_result("error", str(exc) or "Could not open serial port")
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    def _release_own_port(self) -> None:
        ser = self._ser
        self._ser = None
        if ser is None:
            return
        try:
            if getattr(ser, "is_open", False):
                ser.close()
        except Exception:
            pass

    def _probe_omnirig(self, rig_number: int) -> str:
        """Read OmniRig's frequency property. Never assigns Freq (that would retune)."""
        try:
            hz = _read_omnirig_hz(rig_number)
        except ImportError:
            return format_probe_result("unavailable", "pywin32 is not installed")
        except AttributeError:
            return format_probe_result("unverified", "sent, not verified")
        except Exception as exc:
            self._log(f"PROBE_OMNIRIG_FAIL {exc}")
            return format_probe_result("error", f"OmniRig error: {exc}")
        mhz = float(hz) / 1_000_000.0
        self._log(f"PROBE_OMNIRIG ok {mhz}")
        return format_probe_result("ok", f"Read {mhz:.6f} MHz")

    def tune(
        self,
        freq_mhz: float | str,
        confirm: Callable[[str], bool] | None = None,
    ) -> str:
        freq_val = normalize_freq_mhz(freq_mhz)
        msg = f"Tuning to {freq_val} MHz"
        if self.cfg.get("cat_confirm_before_tune") and confirm and not confirm(msg):
            return "cancelled"
        if self.backend() == "omnirig":
            return self._tune_omnirig(freq_val)
        if not CAT_AVAILABLE:
            self._log(f"WOULD_TUNE {freq_val}")
            return "pyserial not installed"
        freq_hz = int(freq_val * 1_000_000)
        profile = self.cfg.get("cat_rig_profile", "kenwood")
        builder = RIG_PROFILES.get(profile, _kenwood_cmd)
        cmd = builder(freq_hz)
        try:
            if not self.connect():
                raise RuntimeError("Could not open serial port")
            self._ser.write(cmd)
            self._log(f"TUNE {freq_val} profile={profile} cmd={cmd!r}")
            return f"Sent CAT: {freq_val} MHz"
        except Exception as e:
            self._log(f"TUNE_FAIL {e}")
            return str(e)
