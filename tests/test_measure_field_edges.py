"""tools/measure_field_edges.py: border-colour edge detection on a synthetic image
(no release screenshot needed to exercise the pure measurement logic)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from tools.measure_field_edges import BORDER_COLOR, main, measure_field_edges


def _draw_field(draw: ImageDraw.ImageDraw, left: int, right: int, top: int, bottom: int) -> None:
    draw.rectangle([left, top, right, bottom], outline=BORDER_COLOR, width=1)


def _synthetic_settings_image() -> Image.Image:
    img = Image.new("RGB", (800, 300), "white")
    draw = ImageDraw.Draw(img)
    _draw_field(draw, 387, 704, 40, 70)
    _draw_field(draw, 387, 704, 90, 120)
    return img


def test_measure_field_edges_finds_both_rows(tmp_path):
    img = _synthetic_settings_image()
    path = tmp_path / "settings-dx-cluster.png"
    img.save(path)

    rows = measure_field_edges(path)
    assert len(rows) == 2
    for _top, left, right in rows:
        assert left == 387
        assert right == 704


def test_main_writes_measurements_file(tmp_path):
    img = _synthetic_settings_image()
    src = tmp_path / "settings-dx-cluster.png"
    out = tmp_path / "settings-dx-cluster-edges.txt"
    img.save(src)

    assert main(["measure_field_edges.py", str(src), str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert text.count("left=387") == 2
    assert "right=704" in text
