"""Content rules. "Invent nothing" is enforced here, not by good intentions.

Levels: error (build fails), warn (reported, build continues), info.
Every rule has a code; tests/fixtures/lint_cases/<code>.yaml triggers each one.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from .loader import GuideData
from .model import (
    BareLine, Calendar, ClaimLine, EditorialLine, Numeral, PlaceholderLine, RangeChart,
    Safety, SessionTable, TagLegend, H2HTable,
)
from .resolve import REF_RE, Item, iter_items, resolve

R_TYPES = {"peer_reviewed", "position_stand", "case_report"}
C_TYPES = {"official_standard", "education", "coaching_blog"}
FREE_STATUSES = {"draft", "sample_sent", "awaiting_answers"}

EDITORIAL_CLAIMY = re.compile(r"\b(stud(y|ies)|research (shows|says|proves|found)|proven|scientifically|science says)\b", re.I)
HAS_NUMBER = re.compile(r"\d|%|\bper ?cent\b", re.I)
RANGE_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|[a-z]+)?\s*(?:–|—|-|to|and)\s*\d", re.I)
NODATA_RE = re.compile(
    r"(couldn[’']t find|could not find|can[’']t find|no (reliable |good |solid )?(data|source|study|studies|research|numbers?)"
    r"|not (been )?(studied|measured|researched)|nobody has (measured|studied)|unknown)", re.I)
PRICE_RE = re.compile(r"[$€£]\s?\d|\b\d+(?:[.,]\d+)?\s?(USD|EUR|GBP|dollars|euros)\b", re.I)
NUM_TOKEN = re.compile(r"\d+(?:[.,]\d+)?")

SAFETY_REQUIRED = {
    "not medical advice": re.compile(r"medical advice", re.I),
    "pain/injury: see a professional": re.compile(r"(doctor|physio|physiotherapist|physical therapist|professional|GP)\b", re.I),
    "stop on sharp pain": re.compile(r"sharp pain", re.I),
}

# (US pattern, UK pattern). Small on purpose: only words that are unambiguous in guide copy.
SPELLING_PAIRS: list[tuple[str, str]] = [
    (r"\bcolor(s|ed|ful)?\b", r"\bcolour(s|ed|ful)?\b"),
    (r"\bfavorite(s)?\b", r"\bfavourite(s)?\b"),
    (r"\bbehavior(s|al)?\b", r"\bbehaviour(s|al)?\b"),
    (r"\bcenter(s|ed)?\b", r"\bcentre(s|d)?\b"),
    (r"\bliter(s)?\b", r"\blitre(s)?\b"),
    (r"\bfiber(s)?\b", r"\bfibre(s)?\b"),
    (r"\bgray\b", r"\bgrey\b"),
    (r"\bdefense\b", r"\bdefence\b"),
    (r"\bjewelry\b", r"\bjewellery\b"),
    (r"\baluminum\b", r"\baluminium\b"),
    (r"\bcatalog\b", r"\bcatalogue\b"),
    (r"\bmom(s)?\b", r"\bmum(s)?\b"),
    (r"\bmath\b", r"\bmaths\b"),
    (r"\bprogram(s)?\b", r"\bprogramme(s)?\b"),
    (r"\btravel(ed|ing|er|ers)\b", r"\btravel(led|ling|ler|lers)\b"),
    (r"\blabel(ed|ing)\b", r"\blabel(led|ling)\b"),
    (r"\bmodel(ed|ing)\b", r"\bmodel(led|ling)\b"),
    (r"\b(organ|real|recogn|priorit|minim|maxim|stabil|mobil|optim|special|emphas|visual|memor|categor)iz(e|es|ed|ing|ation)\b",
     r"\b(organ|real|recogn|priorit|minim|maxim|stabil|mobil|optim|special|emphas|visual|memor|categor)is(e|es|ed|ing|ation)\b"),
    (r"\banalyz(e|es|ed|ing)\b", r"\banalys(e|es|ed|ing)\b"),
]


@dataclass
class LintIssue:
    level: str
    code: str
    message: str
    where: str = ""

    def __str__(self) -> str:
        loc = f" ({self.where})" if self.where else ""
        return f"{self.level.upper():5} {self.code}{loc}: {self.message}"


@dataclass
class PlaceholderInfo:
    kind: str
    page_id: str
    page_no: int
    prompt: str
    label: str | None
    draft: str | None
    where: str


@dataclass
class LintReport:
    issues: list[LintIssue] = field(default_factory=list)
    placeholders: list[PlaceholderInfo] = field(default_factory=list)

    def add(self, level: str, code: str, message: str, where: str = "") -> None:
        self.issues.append(LintIssue(level, code, message, where))

    @property
    def errors(self) -> list[LintIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[LintIssue]:
        return [i for i in self.issues if i.level == "warn"]

    def codes(self, level: str | None = None) -> set[str]:
        return {i.code for i in self.issues if level is None or i.level == level}

    def inventory(self) -> Counter:
        return Counter(p.kind for p in self.placeholders)


# --------------------------------------------------------------------------- helpers

def parse_unicode_range(spec: str) -> list[tuple[int, int]]:
    ranges = []
    for part in (spec or "").split(","):
        part = part.strip().upper().replace("U+", "")
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            ranges.append((int(a, 16), int(b, 16)))
        else:
            ranges.append((int(part, 16), int(part, 16)))
    return ranges


def bad_glyphs(text: str, ranges: list[tuple[int, int]]) -> list[str]:
    if not ranges:
        return []
    out = []
    for ch in dict.fromkeys(text):
        cp = ord(ch)
        if ch in "\n\t":
            continue
        if not any(a <= cp <= b for a, b in ranges):
            out.append(f"{ch!r} U+{cp:04X}")
    return out


def numbers_in(text: str) -> set[float]:
    return {float(n.replace(",", ".")) for n in NUM_TOKEN.findall(text or "")}


def _where(item: Item) -> str:
    return f"{item.page.file}:{item.path}"


# --------------------------------------------------------------------------- main

def lint(data: GuideData) -> LintReport:
    rep = LintReport()
    g = data.guide
    tok = data.theme.tokens
    ltok = tok.get("lint", {})
    res = resolve(data)
    glyph_ranges = parse_unicode_range(tok.get("font", {}).get("unicode_range", ""))
    banned = [re.compile(p, re.I) for p in ltok.get("banned_phrases", {}).get("general", [])]
    if g.niche != "general":
        banned += [re.compile(p, re.I) for p in ltok.get("banned_phrases", {}).get(g.niche, [])]
    creator_pats = [re.compile(p, re.I) for p in ltok.get("creator_fact_patterns", [])]
    wrong_spelling = [re.compile(uk if g.spelling == "US" else us, re.I) for us, uk in SPELLING_PAIRS]

    # ---------------------------------------------------------------- structure
    counts = Counter(g.page_plan)
    for pid, n in counts.items():
        if n > 1:
            rep.add("error", "duplicate-page", f"{pid!r} appears {n} times in page_plan", "guide.yaml:page_plan")
    for pid in g.page_plan:
        if pid not in data.pages:
            rep.add("error", "missing-page", f"page_plan lists {pid!r} but there is no pages/NN-{pid}.yaml",
                    "guide.yaml:page_plan")
    for pid in g.preview_pages:
        if pid not in g.page_plan:
            rep.add("error", "unknown-preview-page", f"preview_pages lists {pid!r}, which is not in page_plan",
                    "guide.yaml:preview_pages")
    for pid, page in data.pages.items():
        if pid not in g.page_plan:
            rep.add("info", "page-not-in-plan", f"{page.file} is not in page_plan (kept, not rendered)", page.file)
    if g.status in FREE_STATUSES and len(g.page_plan) > g.sample_cap_pages:
        rep.add("warn", "scope-creep",
                f"FREE SAMPLE: SCOPE CREEP. {len(g.page_plan)} pages > sample_cap_pages {g.sample_cap_pages}",
                "guide.yaml:page_plan")
    for clash in res.number_clashes:
        rep.add("error", "source-number-clash", clash, "sources.yaml")
    if g.status == "sold":
        rep.add("info", "sold-status", "status is 'sold'. Only MYKO sets this; never assume payment.", "guide.yaml:status")

    # ---------------------------------------------------------------- claims vs sources
    for c in data.claims:
        where = f"claims.yaml:{c.id}"
        srcs = []
        for sid in c.sources:
            s = data.source_by_id.get(sid)
            if not s:
                rep.add("error", "unknown-source", f"claim {c.id!r} cites unknown source {sid!r}", where)
                continue
            if s.consulted_only:
                rep.add("error", "consulted-cited", f"claim {c.id!r} cites {sid!r}, which is marked consulted_only", where)
            srcs.append(s)
        if c.tag == "R":
            if not srcs:
                rep.add("error", "research-source-type", f"R claim {c.id!r} cites nothing", where)
            for s in srcs:
                if s.type not in R_TYPES:
                    rep.add("error", "research-source-type",
                            f"R claim {c.id!r} cites {s.id!r} ({s.type}); R needs peer_reviewed, position_stand or case_report",
                            where)
        elif c.tag == "C":
            ok = {s.id for s in srcs if s.type in C_TYPES}
            if len(ok) < 2:
                rep.add("error", "consensus-sources",
                        f"C claim {c.id!r} needs >= 2 distinct official_standard/education/coaching_blog sources, has {len(ok)}",
                        where)
        elif c.tag == "S":
            if len({s.id for s in srcs}) < 2:
                rep.add("error", "estimate-sources", f"S claim {c.id!r} needs >= 2 sources, has {len(srcs)}", where)
            if not RANGE_RE.search(c.text):
                rep.add("warn", "estimate-range", f"S claim {c.id!r} should show the whole spread as a range", where)
        elif c.tag == "N":
            if c.sources:
                rep.add("error", "nodata-cites", f"N claim {c.id!r} must cite nothing", where)
            if not NODATA_RE.search(c.text):
                rep.add("warn", "nodata-wording",
                        f"N claim {c.id!r} should admit the gap, e.g. \"I couldn't find a reliable source for that\"", where)
        elif c.tag == "E":
            rep.add("error", "experience-written",
                    f"claim {c.id!r} is tagged E. MY EXPERIENCE is placeholder-only; use {{placeholder: creator}}", where)
        _text_checks(rep, c.text, where, banned=banned, creator=creator_pats, spelling=wrong_spelling,
                     glyphs=None, price=g.status in FREE_STATUSES)

    # ---------------------------------------------------------------- page content
    used_claims: set[str] = set()
    used_tags: set[str] = set()
    explained: dict[str, str] = {}
    safety_blocks: list[tuple[Safety, str]] = []
    numeric_editorial: Counter = Counter()
    numeric_editorial_where: dict[int, str] = {}
    known_pages = set(g.page_plan)

    for item in iter_items(data):
        where = _where(item)
        parent = item.parent
        if isinstance(parent, TagLegend) and item.kind == "heading":
            continue
        if item.kind == "claim_ref":
            cid = item.value
            claim = data.claim_by_id.get(cid)
            if not claim:
                rep.add("error", "unknown-claim", f"unknown claim id {cid!r}", where)
                continue
            used_claims.add(cid)
            used_tags.add(claim.tag)
            if isinstance(parent, RangeChart) or type(parent).__name__ in ("RangeRow", "RangeReference"):
                _chart_checks(rep, item, claim, where)
            continue
        if item.kind == "image_ref":
            if item.value not in data.slot_by_id:
                rep.add("error", "unknown-image", f"unknown image slot {item.value!r} (add it to images.yaml)", where)
            continue
        if item.kind == "numeral":
            num: Numeral = item.value
            if isinstance(num.label, ClaimLine):
                claim = data.claim_by_id.get(num.label.claim)
                shown = numbers_in(num.value)
                have = numbers_in(claim.text if claim else "") | numbers_in(num.label.text or "")
                missing = shown - have
                if claim and missing:
                    rep.add("error", "number-not-in-claim",
                            f"numeral {num.value!r} shows {sorted(missing)} which claim {claim.id!r} does not state", where)
            elif HAS_NUMBER.search(num.value) and not isinstance(num.label, PlaceholderLine):
                rep.add("warn", "editorial-number",
                        f"numeral {num.value!r} is not backed by a claim; link its label to a claim or confirm it's an instruction",
                        where)
            _text_checks(rep, num.value, where, banned=banned, creator=creator_pats, spelling=wrong_spelling,
                         glyphs=glyph_ranges, price=g.status in FREE_STATUSES)
            continue

        text = _item_text(item, data)
        if item.kind == "line":
            line = item.value
            if isinstance(line, BareLine):
                rep.add("error", "untagged-line",
                        f"untagged line {line.text[:60]!r}: use {{claim: id}}, {{editorial: true, text: ...}} or a placeholder",
                        where)
            elif isinstance(line, PlaceholderLine):
                pno = res.page_no.get(item.page.id, 0)
                rep.placeholders.append(PlaceholderInfo(line.placeholder, item.page.id, pno, line.prompt,
                                                        line.label, line.draft, where))
                if line.placeholder == "creator":
                    used_tags.add("E")
            elif isinstance(line, EditorialLine):
                bare_text = REF_RE.sub("", line.text)
                if HAS_NUMBER.search(bare_text) or EDITORIAL_CLAIMY.search(bare_text):
                    if line.implicit:
                        key = id(parent)
                        numeric_editorial[key] += 1
                        numeric_editorial_where[key] = where.rsplit(".", 2)[0] if "." in where else where
                    else:
                        rep.add("warn", "editorial-number",
                                f"editorial text has numbers or research wording: {line.text[:70]!r}. "
                                f"If it's a fact, make it a claim.", where)
        elif item.kind == "heading":
            if EDITORIAL_CLAIMY.search(text):
                rep.add("warn", "editorial-number", f"heading uses research wording without a claim: {text[:70]!r}", where)

        is_placeholder = item.kind == "line" and isinstance(item.value, PlaceholderLine)
        _text_checks(rep, text, where, banned=banned, creator=None if is_placeholder else creator_pats,
                     spelling=wrong_spelling, glyphs=glyph_ranges, price=g.status in FREE_STATUSES)
        for ref in REF_RE.findall(text):
            if ref not in known_pages or ref not in data.pages:
                rep.add("error", "unresolved-ref", f"{{ref:{ref}}} points at no page in page_plan", where)

    for key, n in numeric_editorial.items():
        rep.add("warn", "editorial-number",
                f"{n} editorial cell(s) with numbers. Confirm they are instructions, not facts.",
                numeric_editorial_where[key])

    # tags page + safety
    for page in data.plan_pages:
        for i, b in enumerate(page.blocks):
            if b.kind == "tag_legend":
                for code in b.body.tags:
                    explained.setdefault(code, f"{page.file}:blocks[{i}]")
            if b.kind == "safety":
                safety_blocks.append((b.body, f"{page.file}:blocks[{i}]"))
    for code, where in explained.items():
        if code not in used_tags:
            rep.add("warn", "tag-explained-unused",
                    f"tag {code} ({tok['tags'][code]['name']}) is explained but used nowhere. Remove it from the legend.",
                    where)
    if explained:
        for code in sorted(used_tags - set(explained)):
            rep.add("warn", "tag-unexplained", f"tag {code} is used but not explained in the tag legend", "")
    if not safety_blocks:
        rep.add("error", "safety-missing", "no safety block on any page (not medical advice / see a professional / stop on sharp pain)")
    for sb, where in safety_blocks:
        text = " ".join(_line_plain(l, data) for l in sb.items)
        missing = [k for k, rx in SAFETY_REQUIRED.items() if not rx.search(text)]
        if missing:
            rep.add("error", "safety-missing", f"safety block lacks: {', '.join(missing)}", where)

    # unused
    for s in data.sources:
        if not s.consulted_only and s.id not in res.source_no:
            rep.add("warn", "unused-source", f"source {s.id!r} is never cited on a page in page_plan", "sources.yaml")
    for c in data.claims:
        if c.id not in used_claims:
            rep.add("warn", "unused-claim", f"claim {c.id!r} is not used on any page in page_plan", "claims.yaml")

    # guide.yaml + sources: rendered strings need glyph/banned checks too
    for label, text in [("title", g.title), ("kicker", g.kicker), ("audience", g.audience), ("character", g.character),
                        *[(f"cover_title[{i}]", t) for i, t in enumerate(g.cover_title)]]:
        _text_checks(rep, text, f"guide.yaml:{label}", banned=banned, creator=creator_pats,
                     spelling=wrong_spelling, glyphs=glyph_ranges, price=g.status in FREE_STATUSES)
    for s in data.sources:
        if s.id in res.source_no:
            for label, text in (("citation", s.citation), ("venue", s.venue or ""), ("short", s.short or "")):
                bad = bad_glyphs(text, glyph_ranges)
                if bad:
                    rep.add("error", "glyph", f"source {s.id} {label} uses characters outside the font subset: {', '.join(bad)}",
                            "sources.yaml")
    return rep


def _line_plain(line: Any, data: GuideData) -> str:
    if isinstance(line, ClaimLine):
        c = data.claim_by_id.get(line.claim)
        return (line.text or "") + " " + (c.text if c else "")
    if isinstance(line, PlaceholderLine):
        return " ".join(x for x in (line.label, line.draft, line.prompt) if x)
    return getattr(line, "text", "")


def _item_text(item: Item, data: GuideData) -> str:
    if item.kind == "heading":
        return item.value
    return _line_plain(item.value, data).strip()


def _text_checks(rep: LintReport, text: str, where: str, *, banned, creator, spelling, glyphs, price: bool) -> None:
    if not text:
        return
    if "TODO" in text:
        rep.add("error", "todo-left", f"unfinished text: {text[:70]!r}", where)
    for rx in banned:
        m = rx.search(text)
        if m:
            rep.add("error", "banned-phrase", f"banned phrase {m.group(0)!r}", where)
    for rx in creator or ():
        m = rx.search(text)
        if m:
            rep.add("error", "creator-fact",
                    f"{m.group(0)!r} states something about the creator or their audience. "
                    f"Use a {{placeholder: creator}} or {{placeholder: confirm}} instead.", where)
    for rx in spelling:
        m = rx.search(text)
        if m:
            rep.add("warn", "spelling", f"{m.group(0)!r} doesn't match the guide's spelling setting", where)
    if glyphs is not None:
        bad = bad_glyphs(text, glyphs)
        if bad:
            rep.add("error", "glyph", f"characters outside the font subset: {', '.join(bad)}", where)
    if price:
        m = PRICE_RE.search(text)
        if m:
            rep.add("error", "price", f"price {m.group(0)!r} in a free sample", where)


def _chart_checks(rep: LintReport, item: Item, claim: Any, where: str) -> None:
    parent = item.parent
    kind = type(parent).__name__
    if kind == "RangeRow":
        if item.path.endswith(".no_data"):
            if claim.tag != "N":
                rep.add("error", "chart-nodata-tag", f"no_data row must reference an N claim, {claim.id!r} is {claim.tag}", where)
            return
        if claim.tag in ("N", "E"):
            rep.add("error", "chart-invented-bar", f"bar backed by {claim.tag} claim {claim.id!r}. No data means no bar.", where)
        have = numbers_in(claim.text)
        for v in (parent.lo, parent.hi):
            if v is not None and float(v) not in have:
                rep.add("error", "number-not-in-claim",
                        f"bar value {v:g} does not appear in claim {claim.id!r} ({claim.text[:60]!r})", where)
    elif kind == "RangeReference":
        if float(parent.value) not in numbers_in(claim.text):
            rep.add("error", "number-not-in-claim",
                    f"reference line value {parent.value:g} does not appear in claim {claim.id!r}", where)
