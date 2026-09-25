"""Golden test. The real one needs reference/ (the v2 pull-up guide); the harness self-test always runs."""
import shutil
from pathlib import Path

import pytest

from conftest import ROOT
from guidekit import golden
from guidekit.render import build

REFERENCE = ROOT / "reference"
PORTED = ROOT / "guides" / "fitwithiz-first-pullup"


@pytest.mark.browser
def test_harness_self_diff_is_zero_and_detects_changes(showcase, tmp_path, need_browser):
    result = build(showcase)
    assert not result.errors, result.errors
    ref = tmp_path / "ref"
    shutil.copytree(showcase / "out" / "site", ref)
    ref_pngs = golden.render_reference(golden.find_reference_html(ref, tmp_path), tmp_path / "ref-png")
    diffs = golden.compare(ref_pngs, result.pngs["full"], tmp_path / "diff")
    assert len(ref_pngs) == len(result.pngs["full"]) == 14
    assert all(d.diff_pct == 0 for d in diffs)

    css = ref / "style.css"
    css.write_text(css.read_text().replace("--c-bg: #F8F3EC", "--c-bg: #FFFFFF"))
    changed = golden.render_reference(ref / "index.html", tmp_path / "ref-png2")
    diffs = golden.compare(changed, result.pngs["full"], tmp_path / "diff2")
    assert max(d.diff_pct for d in diffs) > 1.0


@pytest.mark.browser
@pytest.mark.skipif(not REFERENCE.exists() or not PORTED.exists(),
                    reason="reference/ or guides/fitwithiz-first-pullup/ missing: golden port not done yet")
def test_reference_pixel_diff(need_browser, tmp_path):
    ref_pngs = golden.render_reference(golden.find_reference_html(REFERENCE, tmp_path), tmp_path / "ref")
    result = build(PORTED)
    assert not result.errors, result.errors
    diffs = golden.compare(ref_pngs, result.pngs["full"], tmp_path / "diff")
    assert len(ref_pngs) == len(result.pngs["full"]) == 13
    over = [(d.no, round(d.diff_pct, 2)) for d in diffs if not d.ok]
    assert not over, f"pages over 1% pixel diff: {over}"
