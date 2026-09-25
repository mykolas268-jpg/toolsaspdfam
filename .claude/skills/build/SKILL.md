---
name: build
description: Render the guide (FULL + PREVIEW PDF, PNGs), run QA and the overflow fit loop, regenerate docs, and review the contact sheets.
argument-hint: <guide-id>
disable-model-invocation: true
---

# /build $ARGUMENTS

1. `guidekit build $ARGUMENTS`
   - Lint errors block the render. Fix them (usually via `/write`) and rerun.
   - The fit loop runs per page: spacing first, then fonts down to their floors (body ≥ 26 px, headlines ≥ 56 px). It reports `fit pNN <id>: …`.
2. **Escalations** (`overflow-escalated`): the page still overflows at minimum spacing and font floors. Propose copy cuts to MYKO:
   - Name the page and the overflowing element from the message.
   - Offer 2 or 3 concrete cuts, ranked. Prefer removing editorial lines, then shortening `text:` display wording.
   - **Never delete a fact or change its meaning to make it fit.** Moving a block to another page is an option; so is splitting a page (watch `sample_cap_pages`).
   - Apply only what MYKO approves, then rebuild.
3. **Look at the contact sheets before calling it done.** Read every `out/qa/full-*.jpg` and `out/qa/preview-*.jpg`. Check for:
   - awkward wraps, a single orphan word on a line, empty pages, crowding;
   - wrong image in a slot, images still pending;
   - pills or refs landing on their own line.
4. Other QA: `needs-upscale` → `/images`; `font-not-loaded` or `image-not-loaded` → fix paths; `pdf-*` → investigate before delivering.
5. Report in 5 lines or fewer:
   - pages and fit adjustments;
   - errors and warnings left;
   - the contact-sheet paths;
   - anything MYKO must decide.

`out/docs/qa-report.md` has the full detail.

## Golden port (one-off, once `reference/` is committed)
This is the acceptance test for the whole tool: the ported v2 pull-up guide must match the reference to ≤ 1% differing pixels per page.
1. Read everything in `reference/`. Unpack `pullup-guide_source.zip` to `out/` (not into the repo). Read `build.py` page functions, `STYLE` tokens and `CHECK_JS`. Compare `CHECK_JS` with `guidekit/qa.py` and port anything missing.
2. Replace the theme fonts with the reference's woff2 files. Take the token values from `STYLE` into `guidekit/themes/default/tokens.yaml`.
3. Create `guides/fitwithiz-first-pullup/` as data. Copy sources, claims and text **verbatim** from the reference HTML and `reference/sources.md`; invent nothing. Copy the final images to `images/`.
4. `guidekit golden fitwithiz-first-pullup --reference reference`. It renders `reference/index.html` locally (don't diff against MYKO's PNGs; OS font rasterisation differs).
5. Tune **CSS only** until every page is ≤ 1%, and explain anything bigger. Don't improve the design during this step. Propose improvements separately afterwards.
6. Show MYKO the contact sheets and the diff table.
