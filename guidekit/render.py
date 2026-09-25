"""Jinja2 → HTML → Playwright (PDF + PNG) with the overflow fit loop."""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import math
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from . import qa
from .loader import PKG_DIR, GuideData, load_guide
from .model import BareLine, ClaimLine, EditorialLine, Page, PlaceholderLine, TAG_NAMES
from .resolve import Resolved, inline_html, line_text, resolve

TEMPLATES = PKG_DIR / "templates"


@dataclass
class PageView:
    page: Page
    no: int
    space: float = 1.0
    font: float = 1.0


def fmt_num(v: float) -> str:
    if float(v).is_integer():
        return str(int(v))
    return f"{v:g}"


# --------------------------------------------------------------------------- CSS from tokens

def tokens_css(tok: dict) -> str:
    c, s, sp, f, fit = tok["color"], tok["size"], tok["space"], tok["font"], tok["fit"]
    pg = tok["page"]
    body_floor, head_floor = fit["body_floor"], fit["headline_floor"]
    floors = {
        "body": body_floor, "lead": body_floor, "small": min(s["small"], body_floor),
        "headline": head_floor, "section_title": head_floor, "cover_title": head_floor,
        "card_title": 34, "numeral": 72, "stat": head_floor, "source": 18,
    }
    urange = f.get("unicode_range")
    out = [f"@page {{ size: {pg['width']}px {pg['height']}px; margin: 0; }}"]
    for role in ("head", "body"):
        spec = f[role]
        for style in ("normal", "italic"):
            if spec.get(style):
                out.append(
                    "@font-face { font-family: \"%s\"; src: url(\"fonts/%s\") format(\"woff2\"); "
                    "font-weight: 100 900; font-style: %s; font-display: block;%s }"
                    % (spec["family"], spec[style], style, f" unicode-range: {urange};" if urange else "")
                )
    root = [f"--page-w: {pg['width']}px", f"--page-h: {pg['height']}px", f"--m: {pg['margin']}px",
            f"--f-head: \"{f['head']['family']}\"", f"--f-body: \"{f['body']['family']}\"",
            f"--r-card: {tok['radius']['card']}px", f"--r-small: {tok['radius']['small']}px"]
    root += [f"--c-{k}: {v}" for k, v in c.items()]
    out.append(":root { " + "; ".join(root) + "; }")
    pv = []
    for k, v in s.items():
        name = k.replace("_", "-")
        if k in floors:
            pv.append(f"--fs-{name}: max({floors[k]}px, calc({v}px * var(--font-scale, 1)))")
        else:
            pv.append(f"--fs-{name}: {v}px")
    for k, v in sp.items():
        pv.append(f"--sp-{k.replace('_', '-')}: calc({v}px * var(--space-scale, 1))")
    pv.append("--sp-card-y: calc(40px * var(--space-scale, 1))")
    pv.append("--sp-card-x: calc(44px * var(--space-scale, 1))")
    out.append(".page { " + "; ".join(pv) + "; }")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- renderer

class Renderer:
    def __init__(self, data: GuideData, res: Resolved):
        self.data, self.res = data, res
        self.tok = data.theme.tokens

    # which pages each output contains
    def pages_for(self, mode: str) -> list[Page]:
        plan = self.data.plan_pages
        if mode == "full":
            return plan
        wanted = list(self.data.guide.preview_pages)
        if self.data.guide.preview_include_sources:
            wanted += [p.id for p in plan if p.type == "sources"]
        return [p for p in plan if p.id in wanted]

    def image_src(self, slot_id: str) -> str | None:
        slot = self.data.slot_by_id.get(slot_id)
        if not slot or not slot.file or slot.status == "placeholder":
            return None
        path = self.data.root / slot.file
        return f"images/{path.name}" if path.exists() else None

    def env(self, mode: str) -> Environment:
        data, res, tok = self.data, self.res, self.tok
        link_refs = mode == "full"
        link_sources = mode == "full" or data.guide.preview_include_sources
        name = data.guide.creator.name

        env = Environment(loader=FileSystemLoader(str(TEMPLATES)), undefined=StrictUndefined,
                          autoescape=True, trim_blocks=False, lstrip_blocks=False)

        def inline(text: str | None) -> Markup:
            return Markup(inline_html(text or "", res, link_refs))

        def kind(line: Any) -> str:
            return {ClaimLine: "claim", EditorialLine: "editorial", PlaceholderLine: "placeholder",
                    BareLine: "bare"}.get(type(line), "other")

        def sup_claim(cid: str | None) -> Markup:
            claim = data.claim_by_id.get(cid or "")
            if not claim:
                return Markup("")
            nums = sorted({res.source_no[s] for s in claim.sources if s in res.source_no})
            if not nums:
                return Markup("")
            if link_sources:
                parts = [f'<a href="#src-{n}">{n}</a>' for n in nums]
            else:
                parts = [str(n) for n in nums]
            return Markup(f'<sup class="refs">{",".join(parts)}</sup>')

        def sup(line: Any) -> Markup:
            return sup_claim(line.claim) if isinstance(line, ClaimLine) else Markup("")

        def tag(line: Any) -> str | None:
            if isinstance(line, ClaimLine):
                c = data.claim_by_id.get(line.claim)
                return c.tag if c else None
            return None

        def claim_tag(cid: str) -> str:
            c = data.claim_by_id.get(cid)
            return c.tag if c else "N"

        def label(key: str) -> str:
            val = tok["labels"].get(key, key.replace("_", " ").title())
            return val.format(name=name) if isinstance(val, str) else val

        def placeholder_label(line: PlaceholderLine) -> str:
            return line.label or tok["labels"]["placeholder"][line.placeholder].format(name=name)

        def groups(blocks: list) -> list[dict]:
            out: list[dict] = []
            for i, b in enumerate(blocks):
                if b.kind == "timeline_step" and out and out[-1]["kind"] == "timeline_step":
                    out[-1]["members"].append(b)
                else:
                    out.append({"kind": b.kind, "members": [b], "start": i})
            return out

        def pct(v: float, ax: Any) -> float:
            span = (ax.max - ax.min) or 1
            return max(0.0, min(100.0, (v - ax.min) / span * 100))

        def ticks(ax: Any) -> list[float]:
            n = int(math.floor((ax.max - ax.min) / ax.step + 1e-9))
            return [ax.min + i * ax.step for i in range(n + 1)]

        cited = [data.source_by_id[s] for s in res.cited_ids]
        env.globals.update(
            tok=tok, guide=data.guide, mode=mode, screen=False, total=res.total,
            source_no=res.source_no, cited_sources=cited,
            preview_footer=tok["labels"]["preview_footer"].format(name=name),
            inline=inline, txt=lambda line: inline(line_text(line, data)), sup=sup, sup_claim=sup_claim,
            tag=tag, claim_tag=claim_tag, kind=kind, label=label, placeholder_label=placeholder_label,
            tag_name=lambda c: tok["tags"].get(c, {}).get("name", TAG_NAMES.get(c, c)),
            tag_explain=lambda c: tok["tags"].get(c, {}).get("explain", "").format(name=name),
            image=lambda sid: {"src": self.image_src(sid)}, groups=groups, pct=pct, ticks=ticks, num=fmt_num,
        )
        return env

    def page_views(self, mode: str, fits: dict[str, qa.PageFit]) -> list[PageView]:
        views = []
        for p in self.pages_for(mode):
            if p.type == "sources":
                p = p.model_copy(update={
                    "title": p.title or self.tok["labels"]["sources_title"],
                    "kicker": p.kicker or self.tok["labels"]["sources_kicker"],
                })
            fit = fits.get(p.id)
            views.append(PageView(p, self.res.page_no[p.id], fit.space if fit else 1.0, fit.font if fit else 1.0))
        return views

    def html(self, mode: str, fits: dict[str, qa.PageFit] | None = None) -> str:
        env = self.env(mode)
        return env.get_template("base.html.j2").render(page_views=self.page_views(mode, fits or {}))

    def write_site(self, site: Path, fits: dict[str, dict[str, qa.PageFit]] | None = None) -> dict[str, Path]:
        fits = fits or {}
        site.mkdir(parents=True, exist_ok=True)
        (site / "style.css").write_text(tokens_css(self.tok) + self.data.theme.css_path.read_text(encoding="utf-8"),
                                        encoding="utf-8")
        fdir = site / "fonts"
        fdir.mkdir(exist_ok=True)
        for spec in (self.tok["font"]["head"], self.tok["font"]["body"]):
            for style in ("normal", "italic"):
                if spec.get(style):
                    shutil.copy2(self.data.theme.fonts_dir / spec[style], fdir / spec[style])
        for lic in self.data.theme.fonts_dir.glob("OFL*.txt"):
            shutil.copy2(lic, fdir / lic.name)
        idir = site / "images"
        if idir.exists():
            shutil.rmtree(idir)
        idir.mkdir()
        for slot in self.data.images.slots:
            src = self.image_src(slot.id)
            if src:
                shutil.copy2(self.data.root / slot.file, idir / Path(slot.file).name)
        paths = {}
        for mode, fname in (("full", "index.html"), ("preview", "preview.html")):
            (site / fname).write_text(self.html(mode, fits.get(mode)), encoding="utf-8")
            paths[mode] = site / fname
        return paths


# --------------------------------------------------------------------------- browser

@contextlib.contextmanager
def browser() -> Iterator[Any]:
    from playwright.sync_api import sync_playwright

    exe = os.environ.get("GUIDEKIT_CHROMIUM") or None
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=exe)
        try:
            yield b
        finally:
            b.close()


def open_page(b: Any, url: str, width: int, height: int) -> Any:
    page = b.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
    page.goto(url, wait_until="load")
    page.evaluate("() => document.fonts.ready.then(() => true)")
    return page


def export(page: Any, pdf: Path, png_dir: Path | None, width: int, height: int) -> list[Path]:
    page.emulate_media(media="print")
    page.pdf(path=str(pdf), width=f"{width}px", height=f"{height}px", print_background=True,
             margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}, prefer_css_page_size=True)
    page.emulate_media(media="screen")
    pngs: list[Path] = []
    if png_dir is not None:
        if png_dir.exists():
            shutil.rmtree(png_dir)
        png_dir.mkdir(parents=True)
        for el in page.query_selector_all("section.page"):
            no = int(el.get_attribute("data-no"))
            pid = el.get_attribute("data-page")
            path = png_dir / f"{no:02d}-{pid}.png"
            el.screenshot(path=str(path))
            pngs.append(path)
    return pngs


# --------------------------------------------------------------------------- build

@dataclass
class BuildResult:
    guide_id: str
    out: Path
    issues: list[qa.Issue] = field(default_factory=list)
    fits: dict[str, dict[str, qa.PageFit]] = field(default_factory=dict)
    checks: dict[str, dict] = field(default_factory=dict)
    pdf_stats: dict[str, dict] = field(default_factory=dict)
    pngs: dict[str, list[Path]] = field(default_factory=dict)
    sheets: list[Path] = field(default_factory=list)
    lint: Any = None
    seconds: float = 0.0

    @property
    def errors(self) -> list[qa.Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[qa.Issue]:
        return [i for i in self.issues if i.level == "warn"]

    @property
    def escalations(self) -> list[qa.PageFit]:
        return [f for f in self.fits.get("full", {}).values() if f.round == 3]


def build(root: Path | str, *, png: bool = True, fit: bool = True, modes: tuple[str, ...] = ("full", "preview"),
          lint_gate: bool = True) -> BuildResult:
    from . import lint as lint_mod

    started = dt.datetime.now()
    data = load_guide(root)
    lint_report = lint_mod.lint(data)
    result = BuildResult(guide_id=data.guide.id, out=data.out, lint=lint_report)
    if lint_gate and lint_report.errors:
        result.issues.extend(qa.Issue("error", "lint", str(i)) for i in lint_report.errors)
        return result

    res = resolve(data)
    r = Renderer(data, res)
    site = data.out / "site"
    tok = data.theme.tokens
    w, h = tok["page"]["width"], tok["page"]["height"]
    families = [tok["font"]["head"]["family"], tok["font"]["body"]["family"]]
    paths = r.write_site(site)

    with browser() as b:
        # 1. fit loop on the full guide; preview pages reuse the same per-page fit
        page = open_page(b, paths["full"].as_uri(), w, h)
        fits_full = qa.fit_loop(page, page.evaluate(qa.CHECK_JS), tok["fit"]) if fit else {}
        page.close()
        result.fits = {"full": fits_full, "preview": fits_full}
        paths = r.write_site(site, result.fits)

        for mode in modes:
            page = open_page(b, paths[mode].as_uri(), w, h)
            check = page.evaluate(qa.CHECK_JS)
            result.checks[mode] = check
            label = "FULL" if mode == "full" else "PREVIEW"
            result.issues += qa.check_issues(check, families, label)
            if mode == "full":
                result.issues += qa.image_resolution_issues(check)
            pdf = data.out / f"{label}.pdf"
            png_dir = data.out / ("png" if mode == "full" else "png-preview") if png else None
            result.pngs[mode] = export(page, pdf, png_dir, w, h)
            page.close()
            expected = len(r.pages_for(mode))
            has_links = mode == "full" and bool(res.source_no or any("{ref:" in json.dumps(p.model_dump(mode="json")) for p in data.plan_pages))
            pdf_issues, stats = qa.pdf_issues(pdf, expected, expect_links=has_links, label=label,
                                              width_pt=w * 0.75, height_pt=h * 0.75)
            result.issues += pdf_issues
            result.pdf_stats[mode] = stats
            for p in result.pngs[mode]:
                if qa.blank_png(p):
                    result.issues.append(qa.Issue("error", "blank-page", f"{label}: {p.name} is blank"))

    for f in result.escalations:
        result.issues.append(qa.Issue("error", "overflow-escalated", f.note, f.id))
    for f in fits_full.values():
        if f.round in (1, 2):
            result.issues.append(qa.Issue("info", "autofit", f.note, f.id))

    qa_dir = data.out / "qa"
    result.sheets = qa.contact_sheets(result.pngs.get("full", []), qa_dir, "full") if png else []
    if png and result.pngs.get("preview"):
        result.sheets += qa.contact_sheets(result.pngs["preview"], qa_dir, "preview")
    result.seconds = (dt.datetime.now() - started).total_seconds()
    (qa_dir / "qa.json").write_text(json.dumps({
        "fits": {m: {k: vars(v) for k, v in fs.items()} for m, fs in result.fits.items()},
        "checks": result.checks, "pdf": result.pdf_stats,
    }, indent=1, default=str), encoding="utf-8")
    return result
