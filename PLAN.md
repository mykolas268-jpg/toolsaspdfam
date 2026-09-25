# guide-factory: plan (Phase 0)

## 0. Blocker, stated first

**`reference/` does not exist.** It's not in this repo, on any branch, or on the remote (the remote has no commits), and it's not in Google Drive. So this plan is built from the build prompt's text alone. That has these consequences:

| Depends on reference | Status | What I do instead |
|---|---|---|
| Porting the pull-up guide to data (`guides/fitwithiz-first-pullup/`) | **Blocked** | No port. Writing 22 sources and 13 pages from memory would break rule #1 ("invent nothing"). |
| Golden test (≤ 1 % pixel diff) | **Blocked** | Build the harness (`guidekit golden`). It runs as soon as `reference/` is committed; the test is skipped while it's missing. |
| Visual design of the components | **Approximated** | Built from the spec's tokens (colors, type scale, 72 px margins). Expect a CSS-tuning pass once the reference is here. |
| Fonts | **Substituted** | Inter and Fraunces variable woff2, Latin subset, from Google Fonts (OFL). These are probably the same files but that's unverified; swap in the reference's files once they're here. |
| Delivery email tone | **Approximated** | Template written from the spec's feature list; compare it against `reference/delivery-email.md`. |
| `CHECK_JS` port | **Re-implemented** | Written from the spec's description (usage, X/Y overflow with element names, clipped cards, fonts, images). |

Everything else (data model, linter, QA, docs, delivery, CLI, skills, tests, the dry run) doesn't depend on the reference and gets built fully.

**Unblocking step:** commit `reference/` (the zips unpacked as given), then run the procedure in `.claude/skills/build/SKILL.md` → "Golden port".

## 1. File tree

```
guide-factory/  (repo root)
├─ CLAUDE.md                     rules only (section 10 of the brief)
├─ README.md                     ≤15-line quickstart
├─ PLAN.md                       this file
├─ pyproject.toml                `pip install -e .` → `guidekit` command
├─ .claude/
│  ├─ skills/{new-guide,research,write,images,build,revise,deliver}/SKILL.md
│  └─ agents/researcher.md
├─ guidekit/
│  ├─ cli.py        new | lint | build | preview | docs | deliver | status | golden | images | log
│  ├─ model.py      pydantic schemas (guide, sources, claims, assumptions, images, log, pages, blocks)
│  ├─ loader.py     folder → validated GuideData (errors carry file + field path)
│  ├─ resolve.py    page numbers, source numbers, {ref:…}, claim → superscripts
│  ├─ render.py     Jinja2 → HTML → Playwright (PDF + PNG), fit loop
│  ├─ qa.py         CHECK_JS, PDF checks (pypdf), image-resolution check, contact sheets
│  ├─ lint.py       content rules (section 6)
│  ├─ docs.py       sources.md, assumptions.md, creator-input-list.md, qa-report.md
│  ├─ deliver.py    email.md, dm.txt, summary.md, zips
│  ├─ images.py     prompt builder, batch contact sheets, crops
│  ├─ golden.py     reference render + pixel diff
│  ├─ templates/base.html.j2, components/*.j2, pages/*.j2
│  └─ themes/default/  tokens.yaml, base.css, fonts/
├─ templates/delivery/  email.md.j2, dm.txt.j2
├─ guides/<id>/      guide.yaml sources.yaml claims.yaml assumptions.yaml images.yaml log.yaml
│                    pages/NN-<id>.yaml  images/  (images/raw/ + out/ gitignored)
└─ tests/            fixtures/minimal (lint-clean guide), fixtures/showcase (every page type),
                     fixtures/lint_cases/*.yaml (one per rule), test_*.py
```

**Changes from the brief's tree, with reasons:**
- `log.yaml` (new): holds the change log and QA log. Both are machine-appended, and round-tripping `assumptions.yaml` through a YAML writer would strip its comments. `assumptions.md` still renders all three.
- `loader.py`, `resolve.py`, `images.py` and `golden.py` split out of `render.py`/`cli.py` so each can be tested alone.
- `guidekit golden`, `guidekit images` and `guidekit log` are extra CLI verbs the skills need (golden diff, prompt building and contact sheets, change-log append).

## 2. Data model (pydantic; YAML is the source of truth)

`guide.yaml` follows the brief, plus these fields:
- `niche: fitness`: selects the banned-phrase list.
- `preview_include_sources: false`
- `safety_page: tags`: which page must carry the safety block.

Unknown keys are an error (`extra="forbid"`), so typos fail loudly.

`sources.yaml` and `claims.yaml` follow the brief exactly. `claims[].tag` ∈ R C E S N; `E` is rejected by lint (placeholder-only).

`assumptions.yaml`:
```yaml
- id: spelling
  decision: "US spelling"
  why: "brief is silent; creator writes 'gym' and 'program'"
  risk: low            # low | medium | high
  confirm: false       # true → becomes a creator question
  date: 2026-09-25
```

`images.yaml`: `style_lock`, `character_override`, `cover_ref`, `credits_used`, and `slots[]`. Each slot has: `id`, `scene`, `action`, `view`, `checks[]`, `file`, `status` (todo|generated|picked|placeholder), `prompt` (generated) and `jobs[]` (`id`, `variant`, `file`, `verdict`, `reason`, `credits`).

`log.yaml`: `changes[]` (`date`, `instruction`, `summary`, `knock_on[]`) and `qa[]` (`date`, `result`, `pages`, `warnings`, `errors`).

### Pages
A page is `pages/NN-<id>.yaml`. The file name supplies the id; the `NN` prefix is only for sorting in a file browser, because `page_plan` in `guide.yaml` decides order and numbering.

```yaml
type: ladder                     # layout variant (13 types)
kicker: "The ladder · part 1"    # headings = plain strings (linted as editorial)
title: "Build the hang first"
lede: {editorial: true, text: "Work down the list. Move on only when you hit the checkpoint on {ref:checklist}."}
blocks:                          # ordered list of components
  - timeline_step:
      n: 1
      title: Dead hang
      image: dead-hang           # images.yaml slot id → placeholder box if no file yet
      builds: {claim: hang-grip}
      start: {editorial: true, text: "3 × 10–20 s hangs"}
      move_on_when: {editorial: true, text: "…"}
```

**Line**: the atomic unit every component uses for body text. There are exactly three kinds:
- `{claim: <id>, text?: "display wording"}`: renders the tag pill and superscript refs from the claim.
- `{editorial: true, text: "…"}`: an instruction or opinion. No tag.
- `{placeholder: creator|photo|cta|confirm, prompt: "…"}`: a typed gap the creator fills. `creator` is the only way MY EXPERIENCE (E) appears.

A bare string where a Line is expected is a lint **failure** (`untagged-line`), not a schema error, so the message points at file:field. Headings (`kicker`, `title`, table headers, labels) are plain strings, and they still go through the banned-phrase, creator-fact, spelling, glyph and editorial-number checks.

Inline markup in any text: `{ref:<page-id>}` becomes "page N" (a link in the FULL PDF), `**bold**` and `*em*`. That's all.

## 3. Components (Jinja macros in `templates/components/`)

| Group | Macro | Key fields |
|---|---|---|
| Text | `tag_pill`, `refs`, `line`, `fact_list`, `card`, `verdict`, `myth` | lines + `tag` from claim |
| Charts | `level_scale` | `levels[]`, `marker` (index or value), `caption` |
| | `range_chart` | `axis{min,max,step,unit_label}`, `rows[{label, claim, lo, hi} \| {label, no_data: claim}]`, `reference{value, label, claim}` (dashed) |
| | `dark_box` | `numerals[{value, label: Line}]` |
| | `stat_row` | `stats[{value, label: Line}]` |
| Structure | `section_opener` | `n`, `title`, `lines` |
| | `timeline_step` | `n`, `title`, `image`, `builds`, `start`, `move_on_when` |
| | `ready_checklist` | `title`, `items: Line[]` |
| | `h2h_table` | `columns[]`, `rows[{label, cells: Line[]}]` |
| Plans | `calendar` | `weeks`, `days[]`, `cells` (grid of level keys), `legend{key: label}` |
| | `session_table` | `title`, `columns[]`, `rows[[Line]]` |
| | `rules` | `items: Line[]` |
| | `checklist` | `items: Line[]` (tick boxes) |
| | `tracker` | `columns[]`, `rows: int` (blank grid) |
| Creator | `placeholder_box`, `photo_frame`, `cta_box` | placeholder Lines |
| Chrome | `sources_list` (auto), `footer` (auto) | computed |

Ticks, flags and arrows are inline SVG, never glyphs, because the fonts are Latin subsets.

## 4. Page types

`cover`, `short_version`, `at_a_glance`, `tags_safety`, `section_opener`, `ladder`, `head_to_head`, `plan`, `myths`, `story`, `checklist`, `next_step`, `sources`.

A page type is a **layout variant** (header style, background, special regions) plus required fields. Body content is always `blocks:`, so any component can appear on any page. `cover` reads `cover_title`, `kicker` and `creator` from `guide.yaml`. `tags_safety` renders only the tag explainers listed in `tags:` plus a required `safety` block. `sources` is generated entirely from `sources.yaml` (numbered, with a flag on biased sources).

### Mapping of the 13 reference pages (**inferred** from `page_plan` ids + component list; not verified against the PNGs)

| # | id | type | components (inferred) |
|---|---|---|---|
| 1 | cover | cover | kicker, cover_title, hero image |
| 2 | short | short_version | fact_list (tagged), verdict |
| 3 | glance | at_a_glance | level_scale, stat_row, dark_box |
| 4 | tags | tags_safety | tag explainers, safety card |
| 5 | why | section_opener | section_opener, range_chart (NO DATA rows, dashed reference) |
| 6 | ladder-1 | ladder | timeline_step ×3 |
| 7 | ladder-2 | ladder | timeline_step ×2, ready_checklist |
| 8 | h2h | head_to_head | h2h_table, verdict |
| 9 | plan | plan | calendar, session_table, rules |
| 10 | myths | myths | myth ×4–5 with severity |
| 11 | checklist | checklist | checklist, tracker |
| 12 | next | next_step | cta_box, placeholder_box, photo_frame |
| 13 | sources | sources | sources_list |

`story` is unused in the reference. Inference: the v2 deletion of the MY EXPERIENCE content removed it.

## 5. Computed, never typed

- **Page number** = index in `page_plan`. The footer reads `NN / TOTAL`.
- **Source number** = the fixed `number` if set; otherwise auto-assigned by first use in page order. Numbers skip the fixed ones, and a collision is a lint error.
- **`{ref:id}`** resolves to `page N`. An unknown id fails lint.
- **Preview** = the `preview_pages` subset. Footers keep the full-guide numbers (`03 / 13`, which tells the creator how big the full guide is) plus "Preview · draft for <name>", and the cover gets a tag. Refs render as plain text unless `preview_include_sources: true`.

## 6. Render and QA pipeline

1. `load → lint`. Errors stop the build; warnings go to the report.
2. Jinja renders `out/site/{index.html, preview.html, style.css, fonts/, images/}`. The same tree gets zipped as `source.zip`.
3. Playwright (Chromium, 1080×1920 viewport, dsf 1):
   - Waits for `document.fonts.ready`, then runs `CHECK_JS`.
   - **Fit loop, per page, max 3 rounds.** Round 1 tightens spacing (`--space-scale` 1 → 0.85 → 0.7). Round 2 shrinks fonts (`--font-scale`, CSS `max()` keeps body ≥ 26 px and headlines ≥ 56 px). Round 3 escalates to MYKO with page, element and px over. Copy is never cut automatically.
   - Writes the fit values back into the HTML, then produces the PDF (`page.pdf(width=1080px, height=1920px, print_background, margin 0, prefer_css_page_size)`) and one PNG per page.
4. The pypdf checks follow the brief: page count, blank pages, 810×1440 pt, link annotations (full), extractable text.
5. Image check: native width ≥ 1.5 × displayed width.
6. Contact sheets: 4 pages per JPG into `out/qa/`.
7. `qa-report.md` and a `log.yaml` QA entry, deduped so identical runs don't spam the log.

## 7. Lint rules (codes are used in tests and reports)

| Code | Rule | Level |
|---|---|---|
| untagged-line | Line is a bare string / lacks claim/editorial/placeholder | fail |
| editorial-number | editorial or heading text with number, %, "study", "research shows", "proven" | warn |
| research-source-type | R cites non peer_reviewed/position_stand/case_report | fail |
| consensus-sources | C needs ≥2 distinct official_standard/education/coaching_blog | fail |
| estimate-sources | S needs ≥2 sources | fail |
| estimate-range | S text shows no range | warn |
| nodata-cites | N cites a source | fail |
| nodata-wording | N text doesn't admit the gap | warn |
| experience-written | claim tagged E | fail |
| unknown-claim / unknown-source / unknown-image | id not found | fail |
| unused-source | source never cited on a rendered page | warn |
| unused-claim | claim never used | warn |
| tag-explained-unused | tags page explains a tag used nowhere | warn |
| creator-fact | "you ask me", "my followers", "I did", "I was", "when I started", … outside placeholders | fail |
| banned-phrase | per-niche list from theme | fail |
| spelling | US/UK mismatch vs `guide.spelling` | warn |
| unresolved-ref | `{ref:x}` where x ∉ page_plan | fail |
| missing-page | page_plan id without a page file | fail |
| scope-creep | pages > sample_cap_pages | warn (loud) |
| glyph | character outside font subset (→ ✓ ⚑ …) | fail |
| price | currency amount while status ≠ paid_discussion/sold | fail |
| safety-missing | no safety block with the 3 required lines | fail |
| source-number-clash | two sources share a display number | fail |
| sold-status | `status: sold`: printed as a reminder that only MYKO sets it | info |

The placeholder inventory (by kind, with page numbers) is printed on every lint run and feeds `creator-input-list.md`.

## 8. Risks (ranked)

1. **Missing reference (high).** The golden test and acceptance criterion 1 can't pass until it arrives. Templates will need a CSS pass, likely a few hours, to reach ≤ 1 % diff. The data model and the components' *structure* should survive; I can't confirm that without the PNGs.
2. **The 3-hour target (medium–high).** Research with genuine verification of about 20 sources is the bottleneck, plausibly 60–90 min of wall time even with a subagent. Images with QA run 30–60 min at 2 variants per slot. The tool removes the layout, numbering and docs time (the day-long part of v1). It can't make verification faster, and it shouldn't.
3. **Network in this cloud container (medium).** NCBI E-utilities, Europe PMC and Crossref are blocked by the egress policy here. On MYKO's machine they aren't. The Phase 5 dry run can only verify through reachable pages, and any source that can't be opened is excluded, not assumed.
4. **Heuristic lint false positives (medium).** Examples: "I did" inside an instruction, or "program" in UK text. Each rule's docstring says how to rephrase; there is no disable-comment escape hatch, because that would defeat the purpose.
5. **Chromium PDF internals (low).** Internal anchor links become PDF link annotations in current Chromium, and the QA checks for them explicitly.
6. **Windows (low).** Only pathlib, zipfile and Playwright's Python API are used. No shell steps. File URLs come from `Path.as_uri()`.
