# Project summaries and retired question comments

The records producer and strict approval check append an escaped Markdown table
to the runner's `GITHUB_STEP_SUMMARY`. It reports current approvals, candidates
needing decisions, gone approvals, recorded passing checks and review links.
The check writes a failure report before returning a failing status; generation
failures without a usable report produce a short pointer to the job log. No
question code is evaluated by the summary writer.

The trusted preview adapter uses one owned project summary when more than 30
questions need decisions, including gone approvals. It creates no new individual
question comments in this mode. Existing current checklists remain intact so
unrecorded ticks are not silently discarded or extended to new candidates.
Recording those ticks still requires the existing authenticated permission,
current head, candidate hash and artifact gates. A later smaller project resumes
individual comments and updates any existing summary.

When a question disappears from the verified artifact, its owned checklist is
retired rather than deleted. The adapter rereads the latest body immediately
before updating it, preserves the complete previous text and ticks in a fenced
read-only archive, and spaces token openers so the old question marker and
commands cannot be recorded. The archive clearly labels old ticks as unrecorded.
Other people's comments are untouched. Duplicate or ambiguous owned markers and
checked decisions or rejection commands in a summary fail without rewriting
that intent. Oversized archives fail instead of truncating history.

All neutral records and current manifests are verified before the first comment
write. Each update also rechecks the current head and trusted producer. GitHub
has no atomic comment-body compare-and-swap: a human edit after the final read
can still race a PATCH. These source changes do not activate a workflow or make a
live comment, dispatch or deployment. Focused synthetic/fake-API tests cover the
30/31 boundary, retained current ticks, a late tick on a deleted question,
idempotency, proof-before-write failures and escaped job summaries.

Optional teacher presentation uses the component's shared MathML/LaTeX
validator. Checklist lines retain canonical input strings and add validated
LaTeX where available; partial or empty presentation falls back to canonical
input. No second printer, sanitizer or grading call is introduced. Actual GitHub
math rendering remains a live-service acceptance item.
