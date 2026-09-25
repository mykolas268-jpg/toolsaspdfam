"""Golden test: render the reference HTML on this machine, then pixel-diff the ported guide.

Font rasterisation differs by OS, so golden PNGs are always produced locally from
reference/index.html + its own style.css, never taken from MYKO's exported PNGs.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from .render import browser, open_page

PAGE_SELECTORS = (".page", "section.page", ".slide", "section", "article")


@dataclass
class PageDiff:
    no: int
    ref: Path
    ours: Path | None
    diff_pct: float
    diff_img: Path | None

    @property
    def ok(self) -> bool:
        return self.ours is not None and self.diff_pct <= 1.0


def find_reference_html(ref_dir: Path, work: Path) -> Path:
    """reference/index.html, or unpack reference/*source*.zip into work/ and find index.html there."""
    direct = sorted(ref_dir.rglob("index.html"))
    if direct:
        return direct[0]
    zips = sorted(ref_dir.glob("*source*.zip"))
    if not zips:
        raise FileNotFoundError(f"no index.html or *source*.zip under {ref_dir}")
    dest = work / "ref-src"
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zips[0]) as zf:
        zf.extractall(dest)
    found = sorted(dest.rglob("index.html"))
    if not found:
        raise FileNotFoundError(f"{zips[0].name} has no index.html")
    return found[0]


def render_reference(index_html: Path, out_dir: Path, width: int = 1080, height: int = 1920,
                     selector: str | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()
    with browser() as b:
        page = open_page(b, index_html.resolve().as_uri(), width, height)
        chosen = selector
        if not chosen:
            for sel in PAGE_SELECTORS:
                els = page.query_selector_all(sel)
                sized = [e for e in els if (bb := e.bounding_box()) and abs(bb["width"] - width) < 2 and abs(bb["height"] - height) < 2]
                if sized:
                    chosen = sel
                    break
        if not chosen:
            raise RuntimeError(f"no {width}x{height} page elements found in {index_html}; pass --selector")
        paths = []
        for i, el in enumerate(page.query_selector_all(chosen), 1):
            bb = el.bounding_box()
            if not bb or abs(bb["width"] - width) > 2:
                continue
            path = out_dir / f"{i:02d}.png"
            el.screenshot(path=str(path))
            paths.append(path)
        return paths


def pixel_diff(a: Path, b: Path, out: Path, tolerance: int = 24) -> float:
    """Percent of pixels whose max channel difference exceeds `tolerance` (0-255)."""
    from PIL import Image, ImageChops

    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        ib = ib.resize(ia.size)
    diff = ImageChops.difference(ia, ib)
    mask = diff.convert("L").point(lambda v: 255 if v > tolerance else 0)
    changed = sum(1 for v in mask.getdata() if v)
    total = ia.size[0] * ia.size[1]
    vis = Image.blend(ia, Image.new("RGB", ia.size, (255, 255, 255)), 0.6)
    vis.paste((230, 40, 40), mask=mask)
    out.parent.mkdir(parents=True, exist_ok=True)
    vis.save(out)
    return 100.0 * changed / total


def compare(ref_pngs: list[Path], our_pngs: list[Path], diff_dir: Path) -> list[PageDiff]:
    results = []
    for i, ref in enumerate(ref_pngs):
        ours = our_pngs[i] if i < len(our_pngs) else None
        if ours is None:
            results.append(PageDiff(i + 1, ref, None, 100.0, None))
            continue
        dpath = diff_dir / f"{i + 1:02d}-diff.png"
        results.append(PageDiff(i + 1, ref, ours, pixel_diff(ref, ours, dpath), dpath))
    return results
