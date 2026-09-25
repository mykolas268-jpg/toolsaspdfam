---
name: revise
description: Apply a revision instruction to a guide ("delete page 11", "swap myth 2"), rebuild, re-lint, regenerate docs, log the change and report knock-on effects.
argument-hint: <guide-id> "<instruction>"
disable-model-invocation: true
---

# /revise $ARGUMENTS

1. Snapshot the current state: run `guidekit lint <guide-id> -v` and keep the output.
2. Apply the edit in YAML with the smallest possible change:
   - Delete a page: remove its id from `page_plan` (and `preview_pages`). Leave the page file. Page numbers, footers, `{ref:…}` and source numbers recompute on their own.
   - Reorder pages: reorder `page_plan`.
   - Change a fact: edit `claims.yaml`. If the change needs new evidence, run `/research` first.
   - Wording only: edit the page YAML, or a claim's `text:` override.
3. Rebuild with `guidekit build <guide-id>`. This re-lints, re-renders and regenerates docs.
4. Log it:
   `guidekit log <guide-id> "<instruction>" --summary "<what changed>" --knock-on "<effect>" …`
5. Report knock-on effects by diffing the lint output against the snapshot:
   - Tag types now explained but unused (`tag-explained-unused`). Remove them from the legend.
   - Sources or claims now unused (`unused-source`, `unused-claim`). Keep them or drop them; say which.
   - Refs that point at a removed page (`unresolved-ref`). Fix the wording.
   - Preview page count, and the page count vs `sample_cap_pages`.
   - Pages that now overflow or underfill.
6. Show the contact sheet(s) for changed pages.
