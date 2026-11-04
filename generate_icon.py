"""Generate assets/orbitrx.ico (multi-size Windows icon) from drawn shapes.

Run once at dev time; the resulting .ico is committed and reused by PyInstaller
(exe icon), the main window icon, and the Inno Setup installer (SetupIconFile).
"""

from PIL import Image, ImageDraw

BG = (15, 23, 32, 255)       # orbitrx.ui.theme.BG
ACCENT = (79, 195, 247, 255)  # orbitrx.ui.theme.ACCENT
ORBIT = (143, 163, 181, 200)  # orbitrx.ui.theme.MUTED


def _draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(1, size // 16)
    draw.ellipse([pad, pad, size - pad, size - pad], fill=BG)

    center = size / 2
    orbit_w = max(1, size // 24)
    orbit_r = size * 0.36
    draw.ellipse(
        [center - orbit_r, center - orbit_r * 0.55, center + orbit_r, center + orbit_r * 0.55],
        outline=ORBIT, width=orbit_w,
    )

    dot_r = max(2, size * 0.1)
    draw.ellipse([center - dot_r, center - dot_r, center + dot_r, center + dot_r], fill=ACCENT)

    sat_x, sat_y = center + orbit_r * 0.92, center - orbit_r * 0.1
    sat_r = max(1, size * 0.045)
    draw.ellipse([sat_x - sat_r, sat_y - sat_r, sat_x + sat_r, sat_y + sat_r], fill=ACCENT)
    return img


def generate_orbitrx_ico(path: str = "assets/orbitrx.ico") -> str:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base = _draw_icon(256)
    base.save(path, format="ICO", sizes=[(s, s) for s in sizes])
    return path


if __name__ == "__main__":
    out = generate_orbitrx_ico()
    print(f"[OK] Wrote {out}")
