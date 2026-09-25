"""Acceptance 5 + 6: companion docs regenerate from data; delivery drafts follow the rules."""
import datetime as dt

import yaml

from guidekit import docs
from guidekit.cli import main
from guidekit.deliver import render_messages
from guidekit.lint import lint
from guidekit.loader import load_guide
from guidekit.resolve import resolve

DAY = dt.date(2026, 9, 25)


def _ctx(root):
    data = load_guide(root)
    return data, lint(data), resolve(data)


def test_docs_are_deterministic_and_complete(showcase):
    data, rep, res = _ctx(showcase)
    first = [p.read_text() for p in docs.write_docs(data, rep, res, None, DAY)]
    second = [p.read_text() for p in docs.write_docs(data, rep, res, None, DAY)]
    assert first == second
    sources, assumptions, inputs, qa = first
    assert "| Fixture research line: a specific finding" in sources
    assert "Fixture press article about fixture A." in sources.split("## Consulted, not cited")[1]
    assert "21 men, 4 women" in sources.split("## Known weak spots")[1]
    assert "sells_app" in sources
    assert "Brief says Sam coaches beginners" in assumptions
    assert "(page 11, \"How I got here\")" in inputs
    assert "Do not edit" in qa


def test_docs_follow_data_changes(showcase):
    main(["log", str(showcase), "delete page 11", "--summary", "removed story page", "--today", "2026-09-25"])
    data, rep, res = _ctx(showcase)
    text = docs.assumptions_md(data, DAY)
    assert "delete page 11: removed story page" in text


def test_apology_only_when_late(showcase):
    data, rep, res = _ctx(showcase)  # promised_by 2026-09-20
    late = render_messages(data, res, rep, dt.date(2026, 9, 25))["email.md"]
    on_time = render_messages(data, res, rep, dt.date(2026, 9, 19))["email.md"]
    assert "Sorry this is late" in late and "20 September" in late
    assert "Sorry" not in on_time
    for mail in (late, on_time):
        assert mail.startswith("Subject: Your free guide: Fixture guide")
        assert "no price" in mail
        assert "5. How to read" not in mail  # contents are page titles, numbered by page
        assert "4. Every fact carries a tag" in mail
        assert "revenue share" in mail
        assert "export every page as an image" in mail


def test_next_step_paragraph_optional(showcase):
    path = showcase / "guide.yaml"
    g = yaml.safe_load(path.read_text())
    g["email_next_step"] = False
    path.write_text(yaml.safe_dump(g, sort_keys=False))
    data, rep, res = _ctx(showcase)
    assert "revenue share" not in render_messages(data, res, rep, DAY)["email.md"]


def test_ai_disclosure_only_with_images(showcase):
    data, rep, res = _ctx(showcase)
    assert "AI-generated" not in render_messages(data, res, rep, DAY)["email.md"]
    (showcase / "images").mkdir(exist_ok=True)
    (showcase / "images/cover.png").write_bytes(b"x")
    d = yaml.safe_load((showcase / "images.yaml").read_text())
    d["slots"][0]["file"] = "images/cover.png"
    (showcase / "images.yaml").write_text(yaml.safe_dump(d))
    data, rep, res = _ctx(showcase)
    assert "AI-generated" in render_messages(data, res, rep, DAY)["email.md"]


def test_dm_asks_for_email_when_missing(showcase):
    data, rep, res = _ctx(showcase)
    dm = render_messages(data, res, rep, DAY)["dm.txt"]
    assert "best email" in dm and len(dm) < 500


def test_email_never_claims_unverified_sources_were_checked(showcase):
    data, rep, res = _ctx(showcase)
    assert "I opened and checked each one" in render_messages(data, res, rep, DAY)["email.md"]
    path = showcase / "sources.yaml"
    src = yaml.safe_load(path.read_text())
    src[0]["verified_how"] = "search snippet only; page not opened"
    path.write_text(yaml.safe_dump(src, sort_keys=False))
    data, rep, res = _ctx(showcase)
    mail = render_messages(data, res, rep, DAY)["email.md"]
    assert "I opened and checked each one" not in mail
    assert "NOT SENDABLE" in mail
