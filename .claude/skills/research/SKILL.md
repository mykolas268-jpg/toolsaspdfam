---
name: research
description: Research and verify sources for a guide, then write sources.yaml and claims.yaml with one tag per claim. Runs in the researcher subagent.
argument-hint: <guide-id>
disable-model-invocation: true
context: fork
agent: researcher
---

# Research the guide `$ARGUMENTS`

You are working in the guide-factory repo. The guide lives in `guides/$ARGUMENTS/`. Read `guides/$ARGUMENTS/guide.yaml` (topic, audience, niche, page_plan) and `guides/$ARGUMENTS/assumptions.yaml`, and skim the page stubs to see what each page needs.

## Output
1. `guides/$ARGUMENTS/sources.yaml`: verified sources only, schema:
   ```yaml
   - id: youdas-2010              # author-year, lowercase
     citation: "Youdas JW, et al. (2010). Title."
     venue: "J Strength Cond Res"
     url: https://pubmed.ncbi.nlm.nih.gov/21068680/
     short: pubmed/21068680       # what prints on the sources page
     type: peer_reviewed          # peer_reviewed | position_stand | case_report | official_standard | education | coaching_blog | news
     verified_how: "NCBI E-utilities abstract"   # exactly how you opened it
     verified_on: YYYY-MM-DD
     bias: none                   # none | own_plan | sells_app | sells_equipment | sells_service
     says: "1-2 lines: what it actually says, with numbers"
   ```
   Add `consulted_only: true` for sources you read but won't cite (press coverage of a study you cite directly, a page that confirmed nothing new).
2. `guides/$ARGUMENTS/claims.yaml`: one claim per fact the pages will need:
   ```yaml
   - id: chinup-biceps
     tag: R                       # R | C | S | N   (never E)
     text: "Chin-ups work the biceps harder than pull-ups; lats work hard in both."
     sources: [youdas-2010]
     caveat: "21 men, 4 women"    # sample size, population, anything weak
   ```

## Tag rules (lint enforces these; `guidekit lint $ARGUMENTS` must show no claim/source errors)
- **R**: only peer_reviewed, position_stand or case_report sources. Put small samples in `caveat` and in the text if it matters.
- **C**: ≥ 2 distinct official_standard / education / coaching_blog sources that agree.
- **S**: ≥ 2 sources; the text states the whole range ("between 2 and 8"), never a midpoint.
- **N**: cites nothing; text admits the gap: "I couldn't find a reliable source for that."
- Any number a page will show big (charts, numerals) must appear verbatim in the claim text.

## Verification protocol (non-negotiable)
- Open every source you cite and confirm it says exactly what the claim says.
- PubMed pages block automated fetches. Use `curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=<PMID>&rettype=abstract&retmode=text"`. Find PMIDs with `esearch.fcgi?db=pubmed&term=...`.
- Trace every headline to the original study (v2: the "2012 Dayton study" is Flanagan et al. 2003).
- No fabricated citations, PMIDs, DOIs or numbers. If you can't open it, it doesn't go in as a cited source.
- Flag commercial bias: plans, apps, equipment, coaching services.
- Safety: collect niche-specific red flags (e.g. symptoms that mean stop and see a professional) as C claims.
- Stay inside CLAUDE.md content rules: no weight-loss, calorie or body-shape claims.

## Return (keep it short; the files are the deliverable)
- Counts: sources by type, claims by tag.
- **NO DATA list**: every N claim.
- **Weak spots**: small samples, single-study claims, biased sources, press-only numbers.
- Anything you couldn't verify and left out.
