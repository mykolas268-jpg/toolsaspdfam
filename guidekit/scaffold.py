"""`guidekit new`: scaffold guides/<id>/ with a default page plan and stub pages."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import yaml

# page id → page type for the default plans; any id can be mapped explicitly with id:type
DEFAULT_TYPES = {
    "cover": "cover", "short": "short_version", "glance": "at_a_glance", "tags": "tags_safety",
    "why": "section_opener", "ladder": "ladder", "ladder-1": "ladder", "ladder-2": "ladder",
    "h2h": "head_to_head", "plan": "plan", "myths": "myths", "story": "story",
    "checklist": "checklist", "next": "next_step", "sources": "sources",
}
DEFAULT_PLAN = ["cover", "short", "glance", "tags", "why", "ladder", "plan", "myths", "next", "sources"]
PREVIEW_DEFAULT = ["cover", "short", "glance", "ladder", "myths"]

SAFETY_STUB = [
    {"editorial": True, "text": "This guide is general education, not medical advice."},
    {"editorial": True, "text": "If you have pain or an injury, see a doctor or physio before you start."},
    {"editorial": True, "text": "Stop straight away if you feel sharp pain."},
]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def guide_id(handle: str, topic: str) -> str:
    return f"{slugify(handle.lstrip('@'))}-{slugify(topic)}"


def parse_plan(spec: str | None) -> list[tuple[str, str]]:
    if not spec:
        return [(pid, DEFAULT_TYPES[pid]) for pid in DEFAULT_PLAN]
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        pid, _, ptype = part.partition(":")
        ptype = ptype or DEFAULT_TYPES.get(pid) or DEFAULT_TYPES.get(pid.rstrip("-0123456789"))
        if not ptype:
            raise ValueError(f"no default type for page {pid!r}; write it as {pid}:<type>")
        out.append((pid, ptype))
    return out


def stub_page(pid: str, ptype: str, topic: str) -> dict:
    if ptype == "cover":
        return {"type": "cover", "image": "cover", "badge": "Free guide"}
    if ptype == "sources":
        return {"type": "sources"}
    page: dict = {"type": ptype, "kicker": f"TODO kicker ({pid})", "title": f"TODO title ({pid})"}
    if ptype == "section_opener":
        page["section_number"] = "01"
    if ptype == "tags_safety":
        page["blocks"] = [{"tag_legend": {"tags": ["R", "C", "S", "N"]}}, {"safety": {"items": SAFETY_STUB}}]
    else:
        page["blocks"] = [{"p": {"line": {"editorial": True, "text": f"TODO: write from claims.yaml ({topic})."}}}]
    return page


def _dump(path: Path, data, header: str = "") -> None:
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    path.write_text(header + text, encoding="utf-8")


def new_guide(root: Path, handle: str, topic: str, *, name: str | None = None, plan: str | None = None,
              gid: str | None = None, today: dt.date | None = None) -> Path:
    today = today or dt.date.today()
    handle = handle if handle.startswith("@") else f"@{handle}"
    gid = gid or guide_id(handle, topic)
    gdir = root / "guides" / gid
    if gdir.exists():
        raise FileExistsError(f"{gdir} already exists")
    pages = parse_plan(plan)
    (gdir / "pages").mkdir(parents=True)
    (gdir / "images" / "raw").mkdir(parents=True)
    plan_ids = [pid for pid, _ in pages]
    title = topic[:1].upper() + topic[1:]
    _dump(gdir / "guide.yaml", {
        "id": gid,
        "creator": {"handle": handle, "name": name or handle.lstrip("@"), "email": None},
        "title": title,
        "kicker": f"Free guide · {title}",
        "cover_title": [title],
        "topic": topic,
        "audience": "TODO: from the brief only",
        "niche": "general",
        "spelling": "US",
        "theme": "default",
        "character": "TODO: generic character, never modelled on the creator",
        "page_plan": plan_ids,
        "preview_pages": [p for p in PREVIEW_DEFAULT if p in plan_ids][:5] or plan_ids[:3],
        "sample_cap_pages": 10,
        "promised_by": None,
        "status": "draft",
        "cta": {"type": "undecided", "value": None},
        "email_next_step": True,
    }, "# Filled by /new-guide from the brief. Log every decision in assumptions.yaml.\n")
    _dump(gdir / "assumptions.yaml", [
        {"id": "spelling", "decision": "US spelling", "why": "default; brief not yet read", "risk": "low",
         "confirm": False, "date": today},
        *([] if name else [{"id": "creator-name", "decision": f"Creator name unknown, using {handle.lstrip('@')}",
                            "why": "not in the brief", "risk": "medium", "confirm": True, "date": today}]),
    ])
    (gdir / "sources.yaml").write_text("# Filled by /research (researcher subagent). Verified entries only.\n[]\n", encoding="utf-8")
    (gdir / "claims.yaml").write_text("# Filled by /research. One tag per claim: R C S N (E is placeholder-only).\n[]\n", encoding="utf-8")
    _dump(gdir / "images.yaml", {"slots": [{"id": "cover", "scene": "TODO", "action": "TODO", "checks": []}]})
    _dump(gdir / "log.yaml", {"changes": [], "qa": []})
    for i, (pid, ptype) in enumerate(pages, 1):
        _dump(gdir / "pages" / f"{i:02d}-{pid}.yaml", stub_page(pid, ptype, topic))
    return gdir
