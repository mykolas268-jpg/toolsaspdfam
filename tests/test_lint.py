"""Every lint rule has a fixture in tests/fixtures/lint_cases/ that makes it fire."""
import re
from pathlib import Path

import pytest
import yaml

from conftest import FIX, ROOT, copy_fixture
from guidekit.lint import lint
from guidekit.loader import load_guide

CASES = sorted((FIX / "lint_cases").glob("*.yaml"))


def _walk(node, parts):
    for p in parts:
        node = node[int(p)] if isinstance(node, list) else node[p]
    return node


def apply_patch(root: Path, patch: dict) -> None:
    path = root / patch["file"]
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    parts = [p for p in str(patch.get("path", "")).split(".") if p != ""]
    op, value = patch["op"], patch.get("value")
    if op == "append":
        _walk(data, parts).append(value)
    elif op in ("set", "delete"):
        parent = _walk(data, parts[:-1])
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        if op == "set":
            parent[key] = value
        else:
            del parent[key]
    else:
        raise ValueError(op)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def test_minimal_fixture_is_clean():
    rep = lint(load_guide(FIX / "minimal"))
    assert [str(i) for i in rep.issues if i.level != "info"] == []


@pytest.mark.parametrize("case", CASES, ids=[c.stem for c in CASES])
def test_rule_fires(case, tmp_path):
    spec = yaml.safe_load(case.read_text(encoding="utf-8"))
    root = copy_fixture("minimal", tmp_path)
    for patch in spec["patches"]:
        apply_patch(root, patch)
    rep = lint(load_guide(root))
    hits = [i for i in rep.issues if i.code == spec["rule"]]
    assert hits, f"{spec['rule']} did not fire; got {[str(i) for i in rep.issues]}"
    assert any(i.level == spec["level"] for i in hits), [str(i) for i in hits]
    if spec["level"] == "error":
        assert rep.errors


def test_every_rule_code_has_a_case():
    src = (ROOT / "guidekit" / "lint.py").read_text(encoding="utf-8")
    codes = set(re.findall(r'rep\.add\(\s*"(?:error|warn|info)",\s*"([a-z\-]+)"', src))
    covered = {yaml.safe_load(c.read_text(encoding="utf-8"))["rule"] for c in CASES}
    assert codes, "no rule codes found"
    assert codes - covered == set(), f"lint rules without a fixture: {sorted(codes - covered)}"


def test_placeholder_inventory(showcase):
    rep = lint(load_guide(showcase))
    assert dict(rep.inventory()) == {"photo": 1, "creator": 1, "confirm": 1, "cta": 1}
    assert {p.page_no for p in rep.placeholders} == {11, 13}
