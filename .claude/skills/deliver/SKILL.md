---
name: deliver
description: Produce the delivery package (FULL/PREVIEW PDFs, PNG zip, source zip, email + DM drafts, 5-line summary) for MYKO to send by hand.
argument-hint: <guide-id>
disable-model-invocation: true
---

# /deliver $ARGUMENTS

1. `guidekit deliver $ARGUMENTS`. It rebuilds first and refuses if QA has errors. Fix them; use `--force` only if MYKO explicitly accepts a known issue.
2. Read `out/delivery/email.md` and `out/delivery/dm.txt` and check them:
   - Tone: warm, plain, no hype. There's no price and nothing promised.
   - The contents list matches the pages.
   - The questions are voice-note-friendly and each one names its page.
   - The apology line appears only if today is after `promised_by`.
   - The AI-illustration disclosure is present when there are images.
   - The revenue-share paragraph appears only if `email_next_step: true`.
3. If the creator's email is unknown, the DM asks for it. Leave it that way.
4. Show MYKO the 5-line `summary.md`, then list the files in `out/delivery/`.

**Never send, post or upload anything.** Don't change `status`. MYKO sets `sample_sent`, `awaiting_answers` and `paid_discussion` after sending, and only MYKO ever sets `sold`.
