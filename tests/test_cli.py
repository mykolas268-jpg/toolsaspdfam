"""CLI: new, status, images prompts."""
import datetime as dt
import shutil

import yaml

from guidekit.cli import main
from guidekit.lint import lint
from guidekit.loader import load_guide
from guidekit.images import build_prompt, prompt_problems
from guidekit.model import ImageSlot


def test_new_scaffolds_valid_guide(tmp_path, monkeypatch, capsys):
    (tmp_path / "guides").mkdir()
    monkeypatch.chdir(tmp_path)
    assert main(["new", "@test_creator", "first push-up", "--plan", "cover,short,tags,why,ladder,plan,myths,sources"]) == 0
    gdir = tmp_path / "guides" / "test-creator-first-push-up"
    data = load_guide(gdir)  # schema-valid
    assert data.guide.page_plan == ["cover", "short", "tags", "why", "ladder", "plan", "myths", "sources"]
    assert (gdir / "pages" / "03-tags.yaml").exists()
    rep = lint(data)
    assert "todo-left" in rep.codes("error")  # stubs must be written before a build


def test_status_table(tmp_path, monkeypatch, capsys, showcase):
    (tmp_path / "guides").mkdir(exist_ok=True)
    shutil.move(str(showcase), tmp_path / "guides" / "showcase")
    monkeypatch.chdir(tmp_path)
    assert main(["status", "--today", "2026-09-25"]) == 0
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.startswith("showcase"))
    assert "@fixture_creator" in line and "draft" in line and "2026-09-20" in line
    cols = line.split()
    assert cols[4] == "5" and cols[5] == "4" and cols[6] == "14"  # days late, open placeholders, pages


def test_image_prompt_template():
    slot = ImageSlot(id="hang", scene="a gym with a pull-up bar", action="hanging with straight arms, overhand grip",
                     view="Side view")
    p = build_prompt(slot, "young woman with dark hair", "STYLE.", cover=False)
    assert p.startswith("Use the woman from the reference image and the same illustration style. One single illustration")
    assert "Anatomically correct: two arms, two hands, five fingers each. STYLE." in p
    cover = build_prompt(slot, "young woman with dark hair", "STYLE.", cover=True)
    assert "reference image" not in cover
    bad = ImageSlot(id="x", scene="a series of three poses")
    assert prompt_problems(bad)
