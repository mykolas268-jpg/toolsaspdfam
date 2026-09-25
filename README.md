# guide-factory

Creator brief in; mobile-first PDF guide (1080×1920), preview, PNGs, sources/assumptions/creator-input docs and delivery drafts out.
Rules: `CLAUDE.md`. Design and status: `PLAN.md`. Workflow skills: `.claude/skills/`.

## Quickstart (Windows or macOS, Python 3.11+)

```
python -m venv .venv
.venv\Scripts\activate            (macOS: source .venv/bin/activate)
pip install -e ".[test]"
playwright install chromium
python -m pytest                              # 60+ tests, incl. one failing fixture per lint rule
guidekit build tests/fixtures/showcase        # smoke test: every page type → tests/fixtures/showcase/out/
claude                                        # then, in Claude Code:
  /new-guide @handle "topic"   → /research <id> → /write <id> → /images <id> → /build <id> → /deliver <id>
guidekit status                               # all guides: status, promised_by, days late, open placeholders
```

## Notes
- Edits: remove a page id from `page_plan` to delete a page; footers, cross-refs (`{ref:id}`) and source numbers recompute.
- Generated files live in `guides/<id>/out/` (gitignored); never hand-edit them.
- Custom Chromium: set `GUIDEKIT_CHROMIUM=/path/to/chrome` if `playwright install` isn't possible.
- Nothing is ever sent: `/deliver` writes drafts to `out/delivery/`.
