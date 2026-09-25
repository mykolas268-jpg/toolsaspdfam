"""Delivery package: PDFs, PNG zip, source zip, email + DM drafts, 5-line summary.

Drafts only. Nothing here sends, posts or uploads anything.
"""
from __future__ import annotations

import datetime as dt
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import docs
from .lint import LintReport
from .loader import PKG_DIR, GuideData
from .resolve import Resolved


def delivery_templates_dir(start: Path) -> Path:
    for base in [start, *start.parents]:
        cand = base / "templates" / "delivery"
        if (cand / "email.md.j2").exists():
            return cand
    return PKG_DIR.parent / "templates" / "delivery"


def days_late(promised_by: dt.date | None, today: dt.date) -> int:
    if not promised_by:
        return 0
    return max(0, (today - promised_by).days)


def fmt_date(d: dt.date) -> str:
    return f"{d.day} {d:%B}"


def zip_dir(src: Path, dest: Path, exclude_parts: tuple[str, ...] = ("raw",)) -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src)
            if path.is_file() and not any(part in exclude_parts for part in rel.parts):
                zf.write(path, rel.as_posix())
    return dest


def zip_files(files: list[Path], dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
    return dest


@dataclass
class Delivery:
    dir: Path
    files: list[Path] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)


def render_messages(data: GuideData, res: Resolved, lint_report: LintReport, today: dt.date) -> dict[str, str]:
    g = data.guide
    tdir = delivery_templates_dir(data.root)
    env = Environment(loader=FileSystemLoader(str(tdir)), undefined=StrictUndefined, autoescape=False,
                      keep_trailing_newline=True)
    late = days_late(g.promised_by, today)
    ctx = dict(
        guide=g, name=g.creator.name, email=g.creator.email, total=res.total,
        contents=[(n, t) for n, _, t in docs.page_titles(data, res)],
        n_sources=len(res.cited_ids), questions=docs.creator_questions(data, lint_report, res),
        late=late > 0, days_late=late, promised_by=fmt_date(g.promised_by) if g.promised_by else "",
        has_images=any(s.file and (data.root / s.file).exists() for s in data.images.slots),
        preview_pages=len([p for p in g.preview_pages if p in res.page_no]),
        next_step=g.email_next_step,
        all_verified=not any(i.code == "weak-verification" for i in lint_report.issues),
    )
    return {
        "email.md": env.get_template("email.md.j2").render(**ctx).strip() + "\n",
        "dm.txt": env.get_template("dm.txt.j2").render(**ctx).strip() + "\n",
    }


def summary_lines(data: GuideData, res: Resolved, lint_report: LintReport, build, today: dt.date) -> list[str]:
    g = data.guide
    qs = docs.creator_questions(data, lint_report, res)
    risky = [a for a in data.assumptions if a.risk != "low" or a.confirm]
    errors = (build.errors if build else []) + lint_report.errors
    warns = (build.warnings if build else []) + lint_report.warnings
    late = days_late(g.promised_by, today)
    weak = [i for i in lint_report.issues if i.code == "weak-verification"]
    inv = lint_report.inventory()
    n_confirm = sum(1 for a in data.assumptions if a.confirm)
    supply = [f"{v} {k}" for k, v in sorted(inv.items())] + ([f"{n_confirm} assumption(s) to confirm"] if n_confirm else [])
    qa_line = (f"QA: {'FAIL' if errors else 'pass'}, {len(errors)} errors, {len(warns)} warnings; "
               f"drafts in out/delivery (nothing sent).")
    if weak:
        qa_line = (f"NOT SENDABLE: {len(weak)} cited source(s) never opened (forced package). "
                   f"Verify them, then rerun /deliver. {len(errors)} errors, {len(warns)} warnings.")
    return [
        f"DONE: {res.total}-page guide + {len(g.preview_pages)}-page preview for {g.creator.handle}, "
        f"{len(res.cited_ids)} sources, {len(res.claim_order)} claims.",
        f"ASSUMED: {len(data.assumptions)} decisions logged"
        + (f"; check {', '.join(a.id for a in risky)}" if risky else "; none risky") + ".",
        f"CREATOR MUST SUPPLY: {len(qs)} item(s): " + (", ".join(supply) or "nothing") + ".",
        qa_line,
        f"NEXT: MYKO reviews contact sheets, sends email + DM by hand"
        + (f"; {late} day(s) late, apology line included" if late else "") + ".",
    ]


def deliver(data: GuideData, res: Resolved, lint_report: LintReport, build, today: dt.date | None = None) -> Delivery:
    today = today or dt.date.today()
    out = data.out
    ddir = out / "delivery"
    if ddir.exists():
        shutil.rmtree(ddir)
    ddir.mkdir(parents=True)
    d = Delivery(ddir)
    for name in ("FULL.pdf", "PREVIEW.pdf"):
        if (out / name).exists():
            d.files.append(Path(shutil.copy2(out / name, ddir / name)))
    pngs = sorted((out / "png").glob("*.png"))
    if pngs:
        d.files.append(zip_files(pngs, ddir / "PNG-pages.zip"))
    if (out / "site").exists():
        d.files.append(zip_dir(out / "site", ddir / "source.zip"))
    for p in docs.write_docs(data, lint_report, res, build, today):
        d.files.append(Path(shutil.copy2(p, ddir / p.name)))
    for name, text in render_messages(data, res, lint_report, today).items():
        (ddir / name).write_text(text, encoding="utf-8")
        d.files.append(ddir / name)
    d.summary = summary_lines(data, res, lint_report, build, today)
    (ddir / "summary.md").write_text("\n".join(d.summary) + "\n", encoding="utf-8")
    d.files.append(ddir / "summary.md")
    return d
