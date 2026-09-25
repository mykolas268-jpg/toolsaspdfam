---
name: new-guide
description: Scaffold a new creator guide from a brief or DM notes, propose a page plan, fill guide.yaml and log assumptions.
argument-hint: <@handle> "<topic>"  (then paste the brief / DM notes)
disable-model-invocation: true
---

# /new-guide $ARGUMENTS

Goal: `guides/<id>/` exists, `guide.yaml` is filled from the brief, the page plan is proposed, and every decision is logged. About 10 minutes. Don't ask MYKO anything unless truly blocked.

## 1. Scaffold
Parse handle and topic from `$ARGUMENTS`. Everything after them is the brief (it may also follow in the next message).
```
guidekit new <handle> "<topic>" [--name <first name if the brief gives it>] [--plan <ids>]
```
The default plan has 10 pages: `cover, short, glance, tags, why, ladder, plan, myths, next, sources`. For a smaller plan, pass `--plan` with ids from: cover short glance tags why ladder ladder-1 ladder-2 h2h plan myths story checklist next sources (or `id:type`).

## 2. Fill guide.yaml from the brief only
- `creator.name`: only if the brief states it. Otherwise keep the handle and add an assumption with `confirm: true`.
- `title`, `kicker`, `cover_title` (2 to 3 short lines ending in the payoff): plain, benefit-led, no promises or timelines.
- `audience`: copy what the brief says. Don't embellish.
- `niche`: `fitness` if it's training-related (turns on the fitness banned-phrase list); otherwise `general`.
- `spelling`: US unless the brief clearly signals UK ("uni", "programme", £). Log the evidence either way.
- `character`: a generic illustrated character. It must never be modelled on the creator: age range, hair, plain outfit in theme colours (terracotta, teal, sage, cream).
- `promised_by`: only if MYKO promised a date in the notes.
- `preview_pages`: 5 pages that sell the guide (cover, short, glance, one ladder or plan page, myths).
- `status: draft`. Never `sold`.

## 3. Facts about the creator
Anything the brief says about the creator or their audience (credentials, story, results, "my followers ask…") goes into:
- an assumption with `confirm: true`, and
- later, a `{placeholder: confirm, draft: "<what the brief says>", prompt: "Is this right?"}` on the relevant page.

It never becomes guide copy until they approve it.

## 4. Page plan
Propose the plan as a table: `#`, id, type, one-line purpose. Stay ≤ `sample_cap_pages` (10) for a free sample; say what you cut. Update `page_plan` and rename or add the stub files in `pages/` so each id has `NN-<id>.yaml`.

## 5. Log
Append to `assumptions.yaml` (`id`, `decision`, `why`, `risk`, `confirm`, `date`) for every choice: spelling, niche, plan cuts, character, name, anything inferred. When `confirm: true`, also add `question:`, the creator-facing wording. It goes straight into the email, so no internal words like "brief".

## 6. Report (short)
- The plan table.
- Assumptions marked `confirm: true` or `risk: medium|high`.
- Next step: `/research <id>`.
