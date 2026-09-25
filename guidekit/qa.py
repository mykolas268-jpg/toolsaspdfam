"""Render QA: CHECK_JS (in-browser layout checks), PDF checks, image checks, contact sheets.

CHECK_JS is a re-implementation of the v2 build.py check from its spec (the
original file was not available): per-page content usage, X/Y overflow with
element names, clipped boxes, fonts loaded, images loaded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CHECK_JS = r"""
() => {
  const name = (el) => {
    const q = el.closest('[data-qa]');
    const qa = q ? q.getAttribute('data-qa') : '';
    let cls = '';
    if (typeof el.className === 'string' && el.className.trim()) {
      cls = '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.');
    }
    return (qa ? '[' + qa + '] ' : '') + el.tagName.toLowerCase() + cls;
  };
  const px = (v) => parseFloat(v) || 0;
  const out = [];
  for (const pg of document.querySelectorAll('section.page')) {
    const body = pg.querySelector('.pb');
    const bs = getComputedStyle(body);
    const br = body.getBoundingClientRect();
    const lim = {
      top: br.top + px(bs.paddingTop), bottom: br.bottom - px(bs.paddingBottom),
      left: br.left + px(bs.paddingLeft), right: br.right - px(bs.paddingRight),
    };
    let maxBottom = lim.top;
    const overY = {}, overX = {}, clipped = [];
    const keep = (bucket, el, amount) => {
      const q = el.closest('[data-qa]');
      const key = q ? q.getAttribute('data-qa') : name(el);
      const prev = bucket[key];
      if (!prev || amount >= prev.px) bucket[key] = {el: name(el), px: Math.round(amount)};
    };
    for (const el of body.querySelectorAll('*')) {
      if (el.closest('[data-bleed]')) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      const s = getComputedStyle(el);
      if (s.position === 'absolute' && el.closest('.rchart')) { /* chart overlays are bounded by their chart */ }
      maxBottom = Math.max(maxBottom, r.bottom);
      if (r.bottom > lim.bottom + 1) keep(overY, el, r.bottom - lim.bottom);
      const dx = Math.max(r.right - lim.right, lim.left - r.left);
      if (dx > 1) keep(overX, el, dx);
      const hides = (s.overflow + s.overflowX + s.overflowY).includes('hidden') || s.textOverflow === 'ellipsis';
      if (hides && el.tagName !== 'IMG') {
        const dy = el.scrollHeight - el.clientHeight, dw = el.scrollWidth - el.clientWidth;
        if (dy > 2 || dw > 2) clipped.push({el: name(el), px: Math.max(dy, dw)});
      }
    }
    const usable = lim.bottom - lim.top;
    out.push({
      id: pg.dataset.page, no: parseInt(pg.dataset.no, 10),
      usage: Math.round(1000 * (maxBottom - lim.top) / usable) / 1000,
      over_y: Object.values(overY).sort((a, b) => b.px - a.px),
      over_x: Object.values(overX).sort((a, b) => b.px - a.px),
      clipped: clipped,
      space: getComputedStyle(pg).getPropertyValue('--space-scale').trim(),
      font: getComputedStyle(pg).getPropertyValue('--font-scale').trim(),
      pending_images: [...pg.querySelectorAll('[data-qa^="image-pending"]')].map(e => e.getAttribute('data-qa').split(':')[1]),
      broken_refs: pg.querySelectorAll('.ref-broken').length,
    });
  }
  const fonts = [...document.fonts].map(f => ({family: f.family.replace(/["']/g, ''), status: f.status, style: f.style}));
  const images = [...document.images].map(img => {
    const r = img.getBoundingClientRect();
    return {src: img.getAttribute('src'), slot: img.dataset.slot || '', page: (img.closest('section.page') || {dataset: {}}).dataset.page,
            complete: img.complete, nw: img.naturalWidth, nh: img.naturalHeight, dw: r.width, dh: r.height};
  });
  return {pages: out, fonts: fonts, images: images};
}
"""

SET_FIT_JS = """
([id, space, font]) => {
  const pg = document.querySelector(`section.page[data-page="${id}"]`);
  pg.style.setProperty('--space-scale', String(space));
  pg.style.setProperty('--font-scale', String(font));
  return true;
}
"""


@dataclass
class Issue:
    level: str  # error | warn | info
    code: str
    message: str
    page: str | None = None

    def __str__(self) -> str:
        where = f" [{self.page}]" if self.page else ""
        return f"{self.level.upper():5} {self.code}{where}: {self.message}"


@dataclass
class PageFit:
    id: str
    space: float = 1.0
    font: float = 1.0
    round: int = 0  # 0 fits as written, 1 spacing, 2 fonts, 3 escalated
    note: str = ""


def page_fits(p: dict) -> bool:
    return not (p["over_y"] or p["over_x"] or p["clipped"])


def fit_loop(page: Any, check: dict, fit_tokens: dict) -> dict[str, PageFit]:
    """Per overflowing page: round 1 spacing, round 2 fonts (CSS floors hold), round 3 escalate.
    Never touches copy."""
    fits: dict[str, PageFit] = {}
    space_steps = [float(x) for x in fit_tokens.get("space_steps", [1.0, 0.85, 0.7])]
    font_steps = [float(x) for x in fit_tokens.get("font_steps", [1.0, 0.94, 0.88])]
    by_id = {p["id"]: p for p in check["pages"]}

    def measure(pid: str, space: float, font: float) -> dict:
        page.evaluate(SET_FIT_JS, [pid, space, font])
        res = page.evaluate(CHECK_JS)
        return next(p for p in res["pages"] if p["id"] == pid)

    for pid, p in by_id.items():
        if page_fits(p):
            fits[pid] = PageFit(pid)
            continue
        done = False
        for s in space_steps[1:]:
            if page_fits(measure(pid, s, 1.0)):
                fits[pid] = PageFit(pid, s, 1.0, 1, f"spacing tightened to {s:g}")
                done = True
                break
        if done:
            continue
        s = space_steps[-1]
        for f in font_steps[1:]:
            if page_fits(measure(pid, s, f)):
                fits[pid] = PageFit(pid, s, f, 2, f"spacing {s:g}, fonts scaled {f:g} (floors apply)")
                done = True
                break
        if done:
            continue
        last = measure(pid, s, font_steps[-1])
        worst = (last["over_y"] + last["over_x"] + last["clipped"])[:4]
        detail = "; ".join(f"{w['el']} +{w['px']}px" for w in worst)
        fits[pid] = PageFit(pid, s, font_steps[-1], 3,
                            f"still overflows at minimum spacing and font floors: {detail}. Propose copy cuts.")
    return fits


# --------------------------------------------------------------------------- page / image QA

def check_issues(check: dict, required_families: list[str], label: str) -> list[Issue]:
    issues: list[Issue] = []
    for p in check["pages"]:
        for o in p["over_y"]:
            issues.append(Issue("error", "overflow-y", f"{label}: {o['el']} overflows the bottom by {o['px']}px", p["id"]))
        for o in p["over_x"]:
            issues.append(Issue("error", "overflow-x", f"{label}: {o['el']} overflows sideways by {o['px']}px", p["id"]))
        for o in p["clipped"]:
            issues.append(Issue("error", "clipped", f"{label}: {o['el']} clips {o['px']}px of content", p["id"]))
        for slot in p["pending_images"]:
            issues.append(Issue("warn", "image-pending", f"{label}: illustration slot {slot!r} has no picked file", p["id"]))
        if p["broken_refs"]:
            issues.append(Issue("error", "broken-ref", f"{label}: {p['broken_refs']} unresolved cross-reference(s)", p["id"]))
        if p["usage"] < 0.45 and p["id"] not in ("cover",):
            issues.append(Issue("info", "underfilled", f"{label}: content uses {p['usage']:.0%} of the page", p["id"]))
    loaded = {f["family"] for f in check["fonts"] if f["status"] == "loaded"}
    for fam in required_families:
        if fam not in loaded:
            issues.append(Issue("error", "font-not-loaded", f"{label}: font {fam!r} did not load (fallback font in use)"))
    for f in check["fonts"]:
        if f["status"] == "error":
            issues.append(Issue("error", "font-error", f"{label}: font face {f['family']} {f['style']} failed to load"))
    for im in check["images"]:
        if not im["complete"] or im["nw"] == 0:
            issues.append(Issue("error", "image-not-loaded", f"{label}: {im['src']} did not load", im["page"]))
    return issues


def image_resolution_issues(check: dict, min_ratio: float = 1.5) -> list[Issue]:
    """Native pixels must be >= min_ratio x the displayed size (object-fit: cover aware)."""
    issues: list[Issue] = []
    seen: set[tuple[str, str]] = set()
    for im in check["images"]:
        if not im["nw"] or not im["dw"]:
            continue
        scale = max(im["dw"] / im["nw"], im["dh"] / im["nh"] if im["nh"] else 0)
        ratio = 1 / scale if scale else 99
        key = (im["src"], im["page"])
        if ratio < min_ratio and key not in seen:
            seen.add(key)
            issues.append(Issue("warn", "needs-upscale",
                                f"{im['src']} ({im['nw']}x{im['nh']}) shown at {im['dw']:.0f}x{im['dh']:.0f}: "
                                f"{ratio:.2f}x native, needs >= {min_ratio}x", im["page"]))
    return issues


# --------------------------------------------------------------------------- PDF

def pdf_issues(pdf_path: Path, expected_pages: int, *, expect_links: bool, label: str,
               width_pt: float = 810, height_pt: float = 1440) -> tuple[list[Issue], dict]:
    from pypdf import PdfReader

    issues: list[Issue] = []
    reader = PdfReader(str(pdf_path))
    n = len(reader.pages)
    stats: dict[str, Any] = {"pages": n, "links": 0, "text_chars": 0}
    if n != expected_pages:
        issues.append(Issue("error", "pdf-page-count", f"{label}: {n} pages, expected {expected_pages}"))
    for i, pg in enumerate(reader.pages, 1):
        w, h = float(pg.mediabox.width), float(pg.mediabox.height)
        if abs(w - width_pt) > 1 or abs(h - height_pt) > 1:
            issues.append(Issue("error", "pdf-size", f"{label}: page {i} is {w:.0f}x{h:.0f} pt, expected {width_pt:.0f}x{height_pt:.0f}"))
        text = pg.extract_text() or ""
        stats["text_chars"] += len(text.strip())
        contents = pg.get_contents()
        raw = contents.get_data() if contents is not None else b""
        if len(raw) < 200 and not text.strip():
            issues.append(Issue("error", "pdf-blank-page", f"{label}: page {i} looks blank"))
        for annot in pg.get("/Annots") or []:
            obj = annot.get_object()
            if obj.get("/Subtype") == "/Link":
                stats["links"] += 1
    if stats["text_chars"] == 0:
        issues.append(Issue("error", "pdf-no-text", f"{label}: no extractable text (rasterised?)"))
    if expect_links and stats["links"] == 0:
        issues.append(Issue("error", "pdf-no-links", f"{label}: no link annotations (refs/xrefs should be clickable)"))
    return issues, stats


# --------------------------------------------------------------------------- contact sheets

def contact_sheets(pngs: list[Path], out_dir: Path, prefix: str, per_sheet: int = 4, thumb_w: int = 540) -> list[Path]:
    from PIL import Image, ImageDraw

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{prefix}-*.jpg"):
        old.unlink()
    sheets: list[Path] = []
    gap, label_h = 24, 44
    for s in range(0, len(pngs), per_sheet):
        batch = pngs[s:s + per_sheet]
        thumbs = []
        for p in batch:
            im = Image.open(p).convert("RGB")
            h = round(im.height * thumb_w / im.width)
            thumbs.append((p, im.resize((thumb_w, h), Image.LANCZOS)))
        th = max(t.height for _, t in thumbs)
        sheet = Image.new("RGB", (gap + per_sheet * (thumb_w + gap), gap + label_h + th + gap), (60, 60, 60))
        draw = ImageDraw.Draw(sheet)
        for i, (p, t) in enumerate(thumbs):
            x = gap + i * (thumb_w + gap)
            draw.text((x, gap + 8), p.stem, fill=(240, 240, 240))
            sheet.paste(t, (x, gap + label_h))
        path = out_dir / f"{prefix}-{s // per_sheet + 1:02d}.jpg"
        sheet.save(path, quality=88)
        sheets.append(path)
    return sheets


def blank_png(path: Path) -> bool:
    from PIL import Image

    im = Image.open(path).convert("L")
    lo, hi = im.getextrema()
    return hi - lo < 8
