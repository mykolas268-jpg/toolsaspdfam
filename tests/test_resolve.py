"""Acceptance 2: page numbers, footers, cross-refs and source numbers are computed, never typed."""
import re

import yaml

from guidekit.lint import lint
from guidekit.loader import load_guide
from guidekit.render import Renderer
from guidekit.resolve import resolve


def _html(root, mode="full"):
    data = load_guide(root)
    return Renderer(data, resolve(data)).html(mode)


def _set_plan(root, drop):
    path = root / "guide.yaml"
    g = yaml.safe_load(path.read_text(encoding="utf-8"))
    g["page_plan"] = [p for p in g["page_plan"] if p not in drop]
    g["preview_pages"] = [p for p in g["preview_pages"] if p not in drop]
    path.write_text(yaml.safe_dump(g, sort_keys=False), encoding="utf-8")


def footers(html):
    return [(int(a), int(b)) for a, b in re.findall(r'class="pf-no">(\d+) / (\d+)<', html)]


def test_footers_and_refs(showcase):
    html = _html(showcase)
    assert footers(html) == [(n, 14) for n in range(2, 15)]  # cover has no footer
    assert 'href="#page-plan">page 9</a>' in html
    assert 'href="#page-checklist">page 12</a>' in html


def test_deleting_a_page_is_one_line(showcase):
    _set_plan(showcase, {"why"})
    html = _html(showcase)
    assert footers(html) == [(n, 13) for n in range(2, 14)]
    assert 'href="#page-plan">page 8</a>' in html
    assert 'href="#page-checklist">page 11</a>' in html
    assert "page-why" not in html


def test_deleting_story_warns_unused_tag(showcase):
    assert "tag-explained-unused" not in lint(load_guide(showcase)).codes()
    _set_plan(showcase, {"story"})
    rep = lint(load_guide(showcase))
    hits = [i for i in rep.issues if i.code == "tag-explained-unused"]
    assert hits and "MY EXPERIENCE" in hits[0].message
    assert hits[0].level == "warn"


def test_source_numbers_follow_first_use_and_stay_contiguous(showcase):
    data = load_guide(showcase)
    res = resolve(data)
    assert res.source_no["pr-a"] == 1  # first claim on page 2 cites pr-a
    _set_plan(showcase, {"short", "glance"})
    res = resolve(load_guide(showcase))
    assert sorted(res.source_no.values()) == list(range(1, len(res.source_no) + 1))


def test_fixed_source_number_is_respected(showcase):
    path = showcase / "sources.yaml"
    src = yaml.safe_load(path.read_text(encoding="utf-8"))
    next(s for s in src if s["id"] == "off-f")["number"] = 1
    path.write_text(yaml.safe_dump(src, sort_keys=False), encoding="utf-8")
    res = resolve(load_guide(showcase))
    assert res.source_no["off-f"] == 1
    assert res.source_no["pr-a"] == 2
    assert len(set(res.source_no.values())) == len(res.source_no)


def test_preview_refs_not_clickable(showcase):
    html = _html(showcase, "preview")
    assert 'href="#src-' not in html
    assert 'href="#page-' not in html
    assert "Preview · draft for Sam" in html
    assert footers(html)[0] == (2, 14)  # preview keeps full-guide numbering


def test_preview_include_sources_makes_refs_clickable(showcase):
    path = showcase / "guide.yaml"
    g = yaml.safe_load(path.read_text(encoding="utf-8"))
    g["preview_include_sources"] = True
    path.write_text(yaml.safe_dump(g, sort_keys=False), encoding="utf-8")
    html = _html(showcase, "preview")
    assert 'href="#src-1"' in html and 'id="src-1"' in html
