---
name: write
description: Write the guide's pages (pages/*.yaml) from claims.yaml only, then lint until clean.
argument-hint: <guide-id>
disable-model-invocation: true
---

# /write $ARGUMENTS

Fill `guides/$ARGUMENTS/pages/*.yaml` using only `claims.yaml`, editorial lines and placeholders. Then `guidekit lint $ARGUMENTS` until 0 errors. Review every warning and either fix it or say why it stays.

## Line kinds (the only three)
```yaml
- {claim: chinup-biceps}                       # a fact; tag + source numbers render automatically
- {claim: chinup-biceps, text: "Shorter display wording, same meaning"}
- {editorial: true, text: "Instruction or opinion. No facts, no numbers you can't stand behind."}
- {placeholder: creator, prompt: "Voice note: …"}       # MY EXPERIENCE: the only way E appears
- {placeholder: confirm, draft: "What the brief says", prompt: "Is this right?"}
- {placeholder: photo, prompt: "…"}   /   {placeholder: cta, prompt: "…"}
```
A component with `editorial: true` treats its bare strings as editorial (tables, rules, checklists). Numbers in them are still warned about.

## Rules
- Every fact comes from `claims.yaml`. If the page needs a fact that isn't there, stop and run `/research` again. Don't write it inline.
- A `text:` override may shorten a claim, never change its meaning, strength, or numbers.
- Cross-references: `{ref:plan}` (prints "page 9" and links). Never type page numbers.
- Big numbers (dark_box, stat_row, range_chart) must appear in the linked claim's text (lint `number-not-in-claim`).
- NO DATA rows use `no_data: <N-claim>`. Never a bar.
- Tags page: `tag_legend` lists only tags actually used. `safety` block: not medical advice, see a professional for pain or injury, stop on sharp pain, plus niche red flags as claims.
- Voice: warm, direct, second person. First person only for instructions and opinions, never for personal history.
- Page budget (1080×1920, body 31 px): about 5 facts + 1 verdict, or 3 timeline steps, or 4 myth cards, or 1 chart + 1 card. The build's fit loop shrinks spacing and fonts a little; it never cuts copy.

## Component reference
`guidekit/model.py` → `BLOCK_TYPES`. Examples of every component: `tests/fixtures/showcase/pages/`.

## Finish
1. `guidekit lint $ARGUMENTS` shows 0 errors.
2. `guidekit preview $ARGUMENTS` writes the HTML quickly (optional).
3. Report: pages written, warnings left and why, the placeholder inventory. Next: `/images` or `/build`.
