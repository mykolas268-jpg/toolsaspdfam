"""Everything computed, never typed: page numbers, source numbers, cross-refs.

Also the content walker that lint, docs and numbering share, so they all agree
on what is on a page and in which order.
"""
from __future__ import annotations

import html
import re
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Iterator, Literal, Union

from pydantic import BaseModel

from .loader import GuideData
from .model import (
    BareLine, BlockBase, Calendar, ClaimLine, EditorialLine, Numeral, Page, PlaceholderLine,
    LINE_TYPES,
)

REF_RE = re.compile(r"\{ref:([A-Za-z0-9_\-]+)\}")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
EM_RE = re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])")

# Fields whose strings are not prose (layout codes, grid encodings).
_NOLINT_FIELDS = {(Calendar, "cells")}
_SKIP_PAGE_FIELDS = {"type", "id", "file"}


@dataclass
class Item:
    kind: str  # line | heading | claim_ref | image_ref | numeral
    path: str
    value: Any
    page: Page
    parent: Any = None  # the component or model holding the value


def _is_literal(ann: Any) -> bool:
    origin = typing.get_origin(ann)
    if origin is Literal:
        return True
    if origin in (Union, types.UnionType, typing.Annotated, list, tuple, set):
        return any(_is_literal(a) for a in typing.get_args(ann))
    return False


def _ref_kind(field_info: Any) -> str | None:
    extra = field_info.json_schema_extra
    if isinstance(extra, dict) and "ref" in extra:
        return extra["ref"]
    for meta in field_info.metadata:
        extra = getattr(meta, "json_schema_extra", None)
        if isinstance(extra, dict) and "ref" in extra:
            return extra["ref"]
    ann = field_info.annotation
    for a in typing.get_args(ann):
        for meta in getattr(a, "__metadata__", ()):
            extra = getattr(meta, "json_schema_extra", None)
            if isinstance(extra, dict) and "ref" in extra:
                return extra["ref"]
    return None


def walk(page: Page) -> Iterator[Item]:
    """Yield every line, heading and id reference on a page, in reading order."""
    for name, finfo in Page.model_fields.items():
        if name in _SKIP_PAGE_FIELDS:
            continue
        val = getattr(page, name)
        if val is None:
            continue
        if name == "image":
            yield Item("image_ref", "image", val, page, page)
            continue
        if _is_literal(finfo.annotation):
            continue
        yield from _walk_value(val, name, page, page)


def _walk_value(val: Any, path: str, page: Page, parent: Any) -> Iterator[Item]:
    if val is None:
        return
    if isinstance(val, LINE_TYPES):
        yield Item("line", path, val, page, parent)
        if isinstance(val, ClaimLine):
            yield Item("claim_ref", path + ".claim", val.claim, page, val)
        return
    if isinstance(val, str):
        yield Item("heading", path, val, page, parent)
        return
    if isinstance(val, list):
        for i, v in enumerate(val):
            yield from _walk_value(v, f"{path}[{i}]", page, parent)
        return
    if isinstance(val, dict):
        for k, v in val.items():
            yield from _walk_value(v, f"{path}.{k}", page, parent)
        return
    if isinstance(val, BlockBase):
        yield from _walk_value(val.body, f"{path}.{val.kind}", page, val.body)
        return
    if isinstance(val, Numeral):
        yield Item("numeral", path + ".value", val, page, parent)
        yield from _walk_value(val.label, path + ".label", page, val)
        return
    if isinstance(val, BaseModel):
        cls = type(val)
        for name, finfo in cls.model_fields.items():
            sub = getattr(val, name)
            if sub is None or (cls, name) in _NOLINT_FIELDS:
                continue
            ref = _ref_kind(finfo)
            if ref:
                yield Item(f"{ref}_ref", f"{path}.{name}", sub, page, val)
                continue
            if _is_literal(finfo.annotation) or isinstance(sub, (bool, int, float)):
                continue
            yield from _walk_value(sub, f"{path}.{name}", page, val)


def iter_items(data: GuideData, pages: list[Page] | None = None) -> Iterator[Item]:
    for page in data.plan_pages if pages is None else pages:
        yield from walk(page)


# --------------------------------------------------------------------------- numbering

@dataclass
class Resolved:
    page_no: dict[str, int]
    total: int
    source_no: dict[str, int]
    claim_order: list[str]
    claim_pages: dict[str, list[int]] = field(default_factory=dict)
    source_pages: dict[str, list[int]] = field(default_factory=dict)
    number_clashes: list[str] = field(default_factory=list)

    @property
    def cited_ids(self) -> list[str]:
        return sorted(self.source_no, key=self.source_no.__getitem__)


def resolve(data: GuideData) -> Resolved:
    plan = [pid for pid in data.guide.page_plan if pid in data.pages]
    page_no = {pid: i + 1 for i, pid in enumerate(plan)}

    claim_order: list[str] = []
    claim_pages: dict[str, list[int]] = {}
    for item in iter_items(data):
        if item.kind != "claim_ref":
            continue
        cid = item.value
        n = page_no[item.page.id]
        claim_pages.setdefault(cid, [])
        if n not in claim_pages[cid]:
            claim_pages[cid].append(n)
        if cid not in claim_order:
            claim_order.append(cid)

    used_sources: list[str] = []
    source_pages: dict[str, list[int]] = {}
    for cid in claim_order:
        claim = data.claim_by_id.get(cid)
        if not claim:
            continue
        for sid in claim.sources:
            if sid not in data.source_by_id:
                continue
            if sid not in used_sources:
                used_sources.append(sid)
            pages = source_pages.setdefault(sid, [])
            for n in claim_pages[cid]:
                if n not in pages:
                    pages.append(n)

    clashes: list[str] = []
    fixed: dict[int, str] = {}
    for s in data.sources:
        if s.number is not None:
            if s.number in fixed:
                clashes.append(f"sources {fixed[s.number]!r} and {s.id!r} both use number {s.number}")
            fixed[s.number] = s.id
    source_no: dict[str, int] = {}
    nxt = 1
    for sid in used_sources:
        src = data.source_by_id[sid]
        if src.number is not None:
            source_no[sid] = src.number
            continue
        while nxt in fixed:
            nxt += 1
        source_no[sid] = nxt
        nxt += 1

    return Resolved(page_no=page_no, total=len(plan), source_no=source_no,
                    claim_order=claim_order, claim_pages=claim_pages,
                    source_pages={k: sorted(v) for k, v in source_pages.items()},
                    number_clashes=clashes)


# --------------------------------------------------------------------------- inline text

def refs_in(text: str) -> list[str]:
    return REF_RE.findall(text or "")


def plain_text(text: str, res: Resolved) -> str:
    """Text with {ref:x} resolved and markup stripped (for docs, email, lint)."""
    def sub(m: re.Match) -> str:
        n = res.page_no.get(m.group(1))
        return f"page {n}" if n else m.group(0)
    text = REF_RE.sub(sub, text or "")
    text = BOLD_RE.sub(r"\1", text)
    return EM_RE.sub(r"\1", text)


def inline_html(text: str, res: Resolved, link: bool) -> str:
    out = html.escape(text or "", quote=False)
    out = BOLD_RE.sub(r"<strong>\1</strong>", out)
    out = EM_RE.sub(r"<em>\1</em>", out)

    def sub(m: re.Match) -> str:
        pid = m.group(1)
        n = res.page_no.get(pid)
        if not n:
            return f'<span class="ref-broken">{m.group(0)}</span>'
        label = f"page {n}"
        return f'<a class="xref" href="#page-{pid}">{label}</a>' if link else label
    return REF_RE.sub(sub, out)


def line_text(line: Any, data: GuideData) -> str:
    if isinstance(line, ClaimLine):
        if line.text:
            return line.text
        claim = data.claim_by_id.get(line.claim)
        return claim.text if claim else f"[unknown claim {line.claim}]"
    if isinstance(line, (EditorialLine, BareLine)):
        return line.text
    if isinstance(line, PlaceholderLine):
        return line.draft or line.prompt
    return str(line)
