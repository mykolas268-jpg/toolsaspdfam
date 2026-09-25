"""Render + QA with a real browser (skipped when Chromium is unavailable)."""
import yaml
import pytest
from PIL import Image
from pypdf import PdfReader

from guidekit.render import build

pytestmark = pytest.mark.browser


def test_showcase_builds_clean(showcase, need_browser):
    r = build(showcase)
    assert r.errors == [], [str(i) for i in r.errors]
    full, prev = PdfReader(showcase / "out/FULL.pdf"), PdfReader(showcase / "out/PREVIEW.pdf")
    assert len(full.pages) == 14 and len(prev.pages) == 5
    assert float(full.pages[0].mediabox.width) == pytest.approx(810, abs=1)
    assert float(full.pages[0].mediabox.height) == pytest.approx(1440, abs=1)
    assert r.pdf_stats["full"]["links"] > 0 and r.pdf_stats["preview"]["links"] == 0
    assert "Fixture research line" in full.pages[1].extract_text()
    assert len(r.pngs["full"]) == 14
    assert Image.open(r.pngs["full"][0]).size == (1080, 1920)
    assert len([s for s in r.sheets if s.name.startswith("full-")]) == 4  # 4 pages per sheet
    fams = {f["family"] for f in r.checks["full"]["fonts"] if f["status"] == "loaded"}
    assert {"Inter", "Fraunces"} <= fams
    assert {i.code for i in r.warnings} == {"image-pending"}


def _set_myths(root, factor_blocks):
    p = root / "pages/10-myths.yaml"
    d = yaml.safe_load(p.read_text())
    d["blocks"] = factor_blocks(d["blocks"])
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def test_overflow_is_autofixed_by_spacing_first(showcase, need_browser):
    _set_myths(showcase, lambda b: b * 2)  # a little too much (6 myth cards)
    r = build(showcase, png=False)
    f = r.fits["full"]["myths"]
    assert f.round in (1, 2), f
    assert not [i for i in r.errors if i.page == "myths"]


def test_overflow_is_escalated_with_page_and_element(showcase, need_browser):
    _set_myths(showcase, lambda b: b * 3)  # far too much: never cut copy, escalate
    r = build(showcase, png=False)
    f = r.fits["full"]["myths"]
    assert f.round == 3
    esc = [i for i in r.errors if i.code == "overflow-escalated"]
    assert esc and esc[0].page == "myths"
    assert "blk-myth" in esc[0].message and "Propose copy cuts" in esc[0].message
    html = (showcase / "out/site/index.html").read_text()
    assert html.count("Fixture myth number one.") == 3  # copy untouched


def test_lint_errors_block_render(showcase, need_browser):
    p = showcase / "pages/02-short.yaml"
    d = yaml.safe_load(p.read_text())
    d["blocks"][0]["facts"]["items"][0] = "untagged"
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    r = build(showcase)
    assert r.errors and r.errors[0].code == "lint"
    assert not (showcase / "out/FULL.pdf").exists()


def test_low_res_image_flagged(showcase, need_browser):
    img = showcase / "images/cover.png"
    img.parent.mkdir(exist_ok=True)
    Image.new("RGB", (400, 700), (200, 150, 120)).save(img)
    p = showcase / "images.yaml"
    d = yaml.safe_load(p.read_text())
    d["slots"][0].update(file="images/cover.png", status="picked")
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    r = build(showcase, png=False)
    assert any(i.code == "needs-upscale" and i.page == "cover" for i in r.issues)
