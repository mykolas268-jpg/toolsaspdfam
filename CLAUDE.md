# guide-factory

MYKO's done-for-you guide service: creator brief in, mobile-first PDF guide plus companion files out.
**Claude does judgment** (research, verification, writing, image QA). **`guidekit` does repetition** (layout, numbering, lint, QA, docs, packaging).

- A guide is `guides/<id>/`: `guide.yaml`, `sources.yaml`, `claims.yaml`, `assumptions.yaml`, `images.yaml`, `log.yaml`, `pages/NN-<id>.yaml`. Schemas: `guidekit/model.py`.
- Workflow skills (MYKO types them): `/new-guide` → `/research` → `/write` → `/images` → `/build` → `/revise` → `/deliver`.
- Commands: `guidekit new | lint | build | preview | docs | deliver | status | golden | images | log`. Tests: `python -m pytest`.
- Never hand-edit anything in `out/` (generated). Never type page numbers, footers, source numbers or "see page N": write `{ref:<page-id>}`.
- Deleting a page = remove its id from `page_plan`. Then rebuild; lint reports knock-on effects.
- Don't ask MYKO questions mid-run unless truly blocked. Log every decision in the guide's `assumptions.yaml`.

## Tags: every factual line carries exactly one
Factual lines are `{claim: <id>}` pointing at `claims.yaml`. Instructions and opinions are `{editorial: true, text: ...}`. Creator content is a placeholder.
- **RESEARCH (R)**: a peer-reviewed study or a position stand (e.g. ACSM). State the sample size when it's small.
- **COACH CONSENSUS (C)**: standard practice in ≥ 2 reputable coaching or education sources.
- **MY EXPERIENCE (E)**: the creator's own account. **Placeholders only** (`{placeholder: creator, prompt: ...}`); Claude never writes it.
- **ESTIMATE (S)**: a range pulled from several sources. Show the whole spread.
- **NO DATA FOUND (N)**: "I couldn't find a reliable source for that." Never fill the gap with a guess or an invented chart bar.

## Research
- Open every source you cite and confirm it says exactly what the claim says. Record `verified_how`.
- PubMed web pages block automated fetches (reCAPTCHA). Use NCBI E-utilities: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=<PMID>&rettype=abstract&retmode=text`.
- Trace headlines back to the actual study. v2 lesson: the "2012 Dayton study" is Flanagan et al. 2003; the NYT covered it in 2012.
- Flag every source that sells a plan, app, equipment or service (`bias:`).
- No fabricated citations, PMIDs, DOIs or numbers. If a number exists only in press coverage, cite the press source (`type: news`) and say so.
- A source you could not open is not a source. Leave it out, or record it as `consulted_only` with what you could see.
- If a sandbox blocks fetching and only search snippets are available, say so in `verified_how` ("search snippet only; not opened"). Lint warns `weak-verification` and `guidekit deliver` refuses until they're re-opened.

## Creator
- Invent nothing: no backstory, timelines, results, quotes, or claims about their audience.
- If the brief states something about them, it stays a `{placeholder: confirm, draft: "...", prompt: "..."}` until they approve it.
- First-person creator voice is fine for instructions and editorial lines, never for personal claims ("I did", "I was", "you ask me", "my followers" fail lint).

## Content
- No guarantees, no promised timelines, no prices in free samples.
- Fitness: no weight-loss, calorie or body-shape talk. Body mass appears only as performance ("strength relative to body mass").
- Every guide has a safety note: not medical advice; pain or injury, see a professional; stop on sharp pain; niche-specific red flags from the research.
- Spelling follows `guide.yaml` (default US). Log the risk in assumptions when the brief hints otherwise (e.g. "uni").
- Fonts are Latin subsets: no →, ✓, ⚑, ≥, emoji in copy (lint `glyph`). Icons are SVG in templates.

## Scope and sales
- Free samples default to ≤ 10 pages (`sample_cap_pages`); lint warns above that. Push back on scope creep.
- Never set `status: sold` and never assume payment. Only MYKO changes status to sold.
- Never send emails or DMs, never post anything. `/deliver` writes drafts only.

## Code
- Nothing topic-specific in `guidekit/templates` or `themes`: no exercise words, units or labels. All of that comes from YAML.
- Cross-platform: pathlib only, no bash-only pipeline steps (MYKO runs Windows and macOS).
- Every new lint rule needs a failing fixture in `tests/fixtures/lint_cases/` (a meta-test enforces this).
