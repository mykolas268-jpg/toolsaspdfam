"""Load a guide folder into validated models. Errors carry file + field path."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError

from .model import (
    Assumption, Claim, Guide, ImagesFile, ImageSlot, LogFile, Page, Source,
)

PKG_DIR = Path(__file__).resolve().parent
PAGE_FILE_RE = re.compile(r"^(\d+)-(.+)\.ya?ml$")


class LoadError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass
class Theme:
    name: str
    dir: Path
    tokens: dict[str, Any]

    @property
    def css_path(self) -> Path:
        return self.dir / "base.css"

    @property
    def fonts_dir(self) -> Path:
        return self.dir / "fonts"


@dataclass
class GuideData:
    root: Path
    guide: Guide
    sources: list[Source]
    claims: list[Claim]
    assumptions: list[Assumption]
    images: ImagesFile
    log: LogFile
    pages: dict[str, Page]  # every page file, by id
    theme: Theme
    source_by_id: dict[str, Source] = field(init=False)
    claim_by_id: dict[str, Claim] = field(init=False)
    slot_by_id: dict[str, ImageSlot] = field(init=False)

    def __post_init__(self) -> None:
        self.source_by_id = {s.id: s for s in self.sources}
        self.claim_by_id = {c.id: c for c in self.claims}
        self.slot_by_id = {s.id: s for s in self.images.slots}

    @property
    def plan_pages(self) -> list[Page]:
        """Pages in page_plan order; ids without a file are skipped (lint reports them)."""
        return [self.pages[pid] for pid in self.guide.page_plan if pid in self.pages]

    @property
    def out(self) -> Path:
        return self.root / "out"


def read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def write_yaml(path: Path, data: Any) -> None:
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    path.write_text(text, encoding="utf-8")


def _fmt_errors(file: str, exc: ValidationError) -> list[str]:
    out = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        out.append(f"{file}: {loc or '(root)'}: {err['msg']}")
    return out


def _load_model(root: Path, name: str, adapter: TypeAdapter, default: Any, errors: list[str]) -> Any:
    path = root / name
    if not path.exists():
        return adapter.validate_python(default)
    try:
        raw = read_yaml(path)
    except yaml.YAMLError as exc:
        errors.append(f"{name}: YAML error: {exc}")
        return adapter.validate_python(default)
    if raw is None:
        raw = default
    try:
        return adapter.validate_python(raw)
    except ValidationError as exc:
        errors.extend(_fmt_errors(name, exc))
        return adapter.validate_python(default)


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_theme(name: str, overrides: dict[str, Any] | None = None) -> Theme:
    tdir = PKG_DIR / "themes" / name
    if not (tdir / "tokens.yaml").exists():
        raise LoadError([f"theme {name!r} not found in {tdir.parent}"])
    tokens = read_yaml(tdir / "tokens.yaml") or {}
    if overrides:
        tokens = deep_merge(tokens, overrides)
    return Theme(name=name, dir=tdir, tokens=tokens)


def page_id_from_file(path: Path) -> str:
    m = PAGE_FILE_RE.match(path.name)
    return m.group(2) if m else path.stem


def load_guide(root: Path | str) -> GuideData:
    root = Path(root).resolve()
    errors: list[str] = []
    gpath = root / "guide.yaml"
    if not gpath.exists():
        raise LoadError([f"{gpath}: not found (is this a guide folder?)"])
    try:
        guide = Guide.model_validate(read_yaml(gpath))
    except ValidationError as exc:
        raise LoadError(_fmt_errors("guide.yaml", exc)) from None

    sources = _load_model(root, "sources.yaml", TypeAdapter(list[Source]), [], errors)
    claims = _load_model(root, "claims.yaml", TypeAdapter(list[Claim]), [], errors)
    assumptions = _load_model(root, "assumptions.yaml", TypeAdapter(list[Assumption]), [], errors)
    images = _load_model(root, "images.yaml", TypeAdapter(ImagesFile), {}, errors)
    log = _load_model(root, "log.yaml", TypeAdapter(LogFile), {}, errors)

    for label, items in (("sources.yaml", sources), ("claims.yaml", claims),
                         ("assumptions.yaml", assumptions), ("images.yaml slots", images.slots)):
        seen: set[str] = set()
        for it in items:
            if it.id in seen:
                errors.append(f"{label}: duplicate id {it.id!r}")
            seen.add(it.id)

    pages: dict[str, Page] = {}
    pdir = root / "pages"
    for path in sorted(pdir.glob("*.y*ml")) if pdir.exists() else []:
        pid = page_id_from_file(path)
        rel = f"pages/{path.name}"
        if pid in pages:
            errors.append(f"{rel}: duplicate page id {pid!r} (also {pages[pid].file})")
            continue
        try:
            page = Page.model_validate(read_yaml(path) or {})
        except ValidationError as exc:
            errors.extend(_fmt_errors(rel, exc))
            continue
        except yaml.YAMLError as exc:
            errors.append(f"{rel}: YAML error: {exc}")
            continue
        page.id, page.file = pid, rel
        pages[pid] = page

    try:
        theme = load_theme(guide.theme, guide.tokens)
    except LoadError as exc:
        errors.extend(exc.errors)
        theme = None  # type: ignore[assignment]

    if errors:
        raise LoadError(errors)
    return GuideData(root=root, guide=guide, sources=sources, claims=claims,
                     assumptions=assumptions, images=images, log=log, pages=pages, theme=theme)


def dump_model(model: BaseModel) -> Any:
    return model.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
