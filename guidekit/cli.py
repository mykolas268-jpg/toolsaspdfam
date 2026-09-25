"""guidekit CLI: new | lint | build | preview | docs | deliver | status | golden | images | log."""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from .loader import LoadError, load_guide, read_yaml, write_yaml


def find_root(start: Path | None = None) -> Path:
    """Project root = nearest ancestor with a guides/ folder (or pyproject), else cwd."""
    start = (start or Path.cwd()).resolve()
    for base in [start, *start.parents]:
        if (base / "guides").is_dir() or (base / "pyproject.toml").exists():
            return base
    return start


def guide_path(arg: str) -> Path:
    p = Path(arg)
    if (p / "guide.yaml").exists():
        return p.resolve()
    cand = find_root() / "guides" / arg
    if (cand / "guide.yaml").exists():
        return cand.resolve()
    raise SystemExit(f"guide not found: {arg} (pass a folder with guide.yaml or an id under guides/)")


def _today(s: str | None) -> dt.date:
    return dt.date.fromisoformat(s) if s else dt.date.today()


def _print_lint(rep, quiet_info: bool = True) -> None:
    for i in rep.issues:
        if quiet_info and i.level == "info":
            continue
        print(f"  {i}")
    inv = rep.inventory()
    print(f"  placeholders: {sum(inv.values())} ({', '.join(f'{k} {v}' for k, v in sorted(inv.items())) or 'none'})")
    for p in rep.placeholders:
        print(f"    p{p.page_no:02d} {p.kind:<8} {p.prompt[:80]}")


def append_log(root: Path, section: str, entry: dict, dedupe_keys: tuple[str, ...] = ()) -> None:
    path = root / "log.yaml"
    raw = (read_yaml(path) if path.exists() else None) or {}
    raw.setdefault("changes", [])
    raw.setdefault("qa", [])
    items = raw[section]
    if dedupe_keys and items and all(items[-1].get(k) == entry.get(k) for k in dedupe_keys):
        items[-1] = entry
    else:
        items.append(entry)
    write_yaml(path, raw)


# --------------------------------------------------------------------------- commands

def cmd_new(a) -> int:
    from .scaffold import new_guide

    gdir = new_guide(find_root(), a.handle, a.topic, name=a.name, plan=a.plan, gid=a.id)
    print(f"created {gdir}")
    for p in sorted((gdir / "pages").glob("*.yaml")):
        print(f"  {p.name}")
    return 0


def cmd_lint(a) -> int:
    from .lint import lint

    data = load_guide(guide_path(a.guide))
    rep = lint(data)
    print(f"lint {data.guide.id}: {len(rep.errors)} errors, {len(rep.warnings)} warnings")
    _print_lint(rep, quiet_info=not a.verbose)
    return 1 if rep.errors else 0


def cmd_build(a) -> int:
    from . import docs
    from .render import build
    from .resolve import resolve

    root = guide_path(a.guide)
    result = build(root, png=not a.no_png, fit=not a.no_fit)
    rep = result.lint
    data = load_guide(root)
    print(f"build {result.guide_id}: {len(result.errors)} errors, {len(result.warnings)} warnings, {result.seconds:.1f}s")
    if rep.errors:
        print("  lint failed; nothing rendered:")
        _print_lint(rep)
        return 1
    for mode, fits in result.fits.items():
        if mode != "full":
            continue
        for f in fits.values():
            if f.round:
                print(f"  fit p{data.guide.page_plan.index(f.id) + 1:02d} {f.id}: {f.note}")
    for i in result.issues:
        if i.level != "info":
            print(f"  {i}")
    for w in rep.warnings:
        print(f"  lint {w}")
    today = dt.date.today()
    paths = docs.write_docs(data, rep, resolve(data), result, today)
    append_log(root, "qa", {
        "date": today.isoformat(), "result": "fail" if result.errors else ("warn" if result.warnings or rep.warnings else "pass"),
        "pages": len(data.plan_pages), "errors": len(result.errors), "warnings": len(result.warnings) + len(rep.warnings),
        "notes": [f.note for f in result.escalations][:3],
    }, dedupe_keys=("date", "result", "pages", "errors", "warnings"))
    print(f"  out: {result.out / 'FULL.pdf'}, {result.out / 'PREVIEW.pdf'}")
    print(f"  docs: {', '.join(p.name for p in paths)}")
    print("  contact sheets (look at these):")
    for s in result.sheets:
        print(f"    {s}")
    return 1 if result.errors else 0


def cmd_preview(a) -> int:
    from .render import Renderer
    from .resolve import resolve

    data = load_guide(guide_path(a.guide))
    r = Renderer(data, resolve(data))
    paths = r.write_site(data.out / "site")
    for mode, p in paths.items():
        print(f"{mode}: {p.as_uri()}")
    return 0


def cmd_docs(a) -> int:
    from .docs import write_docs
    from .lint import lint
    from .resolve import resolve

    data = load_guide(guide_path(a.guide))
    rep = lint(data)
    for p in write_docs(data, rep, resolve(data), None, _today(a.today)):
        print(p)
    return 0


def cmd_deliver(a) -> int:
    from .deliver import deliver
    from .render import build
    from .resolve import resolve

    root = guide_path(a.guide)
    result = build(root)
    if result.errors and not a.force:
        print(f"deliver blocked: build has {len(result.errors)} errors (run guidekit build, fix, or --force):")
        for i in result.errors[:20]:
            print(f"  {i}")
        return 1
    weak = [i for i in result.lint.issues if i.code == "weak-verification"]
    if weak and not a.force:
        print(f"deliver blocked: {len(weak)} cited source(s) were never opened. Verify them first (or --force for a dry run):")
        for i in weak:
            print(f"  {i}")
        return 1
    data = load_guide(root)
    d = deliver(data, resolve(data), result.lint, result, _today(a.today))
    print(f"delivery drafts in {d.dir} (nothing was sent):")
    for f in d.files:
        print(f"  {f.name}")
    print()
    print("\n".join(d.summary))
    return 0


def cmd_status(a) -> int:
    from .deliver import days_late
    from .lint import lint

    root = find_root()
    today = _today(a.today)
    rows = [("guide", "creator", "status", "promised_by", "late", "open", "pages")]
    for gdir in sorted((root / "guides").glob("*/guide.yaml")):
        try:
            data = load_guide(gdir.parent)
            rep = lint(data)
            g = data.guide
            late = days_late(g.promised_by, today) if g.status == "draft" else 0
            rows.append((g.id, g.creator.handle, g.status, str(g.promised_by or "-"), str(late or "-"),
                         str(len(rep.placeholders)), str(len(g.page_plan))))
        except LoadError as exc:
            rows.append((gdir.parent.name, "?", "INVALID", "-", "-", "-", str(len(exc.errors)) + " errs"))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for j, r in enumerate(rows):
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))
        if j == 0:
            print("  ".join("-" * w for w in widths))
    return 0


def cmd_golden(a) -> int:
    from . import golden
    from .render import build

    root = guide_path(a.guide)
    ref_dir = Path(a.reference).resolve()
    if not ref_dir.exists():
        print(f"reference folder {ref_dir} does not exist; golden test cannot run")
        return 2
    data = load_guide(root)
    work = data.out / "golden"
    index = golden.find_reference_html(ref_dir, work)
    ref_pngs = golden.render_reference(index, work / "ref", selector=a.selector)
    result = build(root)
    ours = result.pngs.get("full", [])
    diffs = golden.compare(ref_pngs, ours, work / "diff")
    worst = 0.0
    print(f"golden: {len(ref_pngs)} reference pages vs {len(ours)} built pages")
    for d in diffs:
        worst = max(worst, d.diff_pct)
        print(f"  page {d.no:02d}: {d.diff_pct:6.2f}% {'ok' if d.ok else 'OVER 1%'}  {d.diff_img or ''}")
    ok = len(ref_pngs) == len(ours) and all(d.ok for d in diffs)
    print("PASS" if ok else "FAIL (explain every page over 1%)")
    return 0 if ok else 1


def cmd_images(a) -> int:
    from . import images

    data = load_guide(guide_path(a.guide))
    if a.action == "prompts":
        rows, problems = images.write_prompts(data)
        for p in problems:
            print(f"ERROR {p}")
        if problems:
            return 1
        for r in rows:
            print(r)
            print()
        return 0
    if a.action == "status":
        print("\n".join(images.status_rows(data.images)))
        return 0
    if a.action == "sheet":
        path = images.batch_sheet(data, a.slot)
        print(path or f"no files for slot {a.slot} in images/raw/")
        return 0 if path else 1
    if a.action == "crop":
        box = tuple(float(x) for x in a.box.split(","))
        print(images.crop(Path(a.file), box, data.out / "qa" / "crops", a.scale))
        return 0
    if a.action == "fetch":
        if not (a.slot and a.job and a.url):
            raise SystemExit("fetch needs --slot, --job and --url")
        print(images.fetch(data, a.slot, a.job, a.url, a.variant, a.credits))
        return 0
    if a.action == "job":
        images.add_job(data, a.slot, a.job, a.file, a.credits, a.variant)
        print(f"recorded job {a.job} on {a.slot}")
        return 0
    if a.action in ("pick", "reject"):
        if a.action == "reject" and not a.reason:
            raise SystemExit("reject needs --reason")
        final = images.set_verdict(data, a.slot, a.job, a.action, a.reason)
        print(f"{a.action} {a.job} on {a.slot}" + (f" -> {final}" if final else ""))
        return 0
    raise SystemExit(f"unknown images action {a.action}")


def cmd_log(a) -> int:
    root = guide_path(a.guide)
    append_log(root, "changes", {"date": _today(a.today).isoformat(), "instruction": a.instruction,
                                 "summary": a.summary or "", "knock_on": a.knock_on or []})
    print(f"logged change in {root / 'log.yaml'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="guidekit", description="Build mobile-first PDF guides from YAML.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="scaffold guides/<id>/")
    p.add_argument("handle")
    p.add_argument("topic")
    p.add_argument("--name", help="creator's first name")
    p.add_argument("--plan", help="comma list of page ids (id or id:type)")
    p.add_argument("--id", help="override the guide id")
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("lint", help="content rules + placeholder inventory")
    p.add_argument("guide")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_lint)

    p = sub.add_parser("build", help="lint, render FULL + PREVIEW (PDF + PNG), QA, fit loop, docs")
    p.add_argument("guide")
    p.add_argument("--no-png", action="store_true")
    p.add_argument("--no-fit", action="store_true")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("preview", help="write the HTML only (fast), print file URLs")
    p.add_argument("guide")
    p.set_defaults(fn=cmd_preview)

    p = sub.add_parser("docs", help="regenerate sources.md, assumptions.md, creator-input-list.md, qa-report.md")
    p.add_argument("guide")
    p.add_argument("--today")
    p.set_defaults(fn=cmd_docs)

    p = sub.add_parser("deliver", help="build + delivery drafts in out/delivery (never sends)")
    p.add_argument("guide")
    p.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    p.add_argument("--force", action="store_true", help="package even if QA has errors")
    p.set_defaults(fn=cmd_deliver)

    p = sub.add_parser("status", help="table of all guides")
    p.add_argument("--today")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("golden", help="render the reference HTML locally and pixel-diff the built guide")
    p.add_argument("guide")
    p.add_argument("--reference", default="reference")
    p.add_argument("--selector", help="CSS selector for page elements in the reference HTML")
    p.set_defaults(fn=cmd_golden)

    p = sub.add_parser("images", help="image pipeline bookkeeping")
    p.add_argument("guide")
    p.add_argument("action", choices=["prompts", "status", "fetch", "sheet", "crop", "job", "pick", "reject"])
    p.add_argument("--url", help="generation result URL (fetch)")
    p.add_argument("--slot")
    p.add_argument("--job")
    p.add_argument("--file")
    p.add_argument("--credits", type=float)
    p.add_argument("--variant", type=int)
    p.add_argument("--reason")
    p.add_argument("--box", help="crop box x,y,w,h (fractions or px)")
    p.add_argument("--scale", type=int, default=2)
    p.set_defaults(fn=cmd_images)

    p = sub.add_parser("log", help="append a change-log entry (used by /revise)")
    p.add_argument("guide")
    p.add_argument("instruction")
    p.add_argument("--summary")
    p.add_argument("--knock-on", action="append")
    p.add_argument("--today")
    p.set_defaults(fn=cmd_log)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except LoadError as exc:
        print("guide has schema errors:")
        for e in exc.errors:
            print(f"  {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
