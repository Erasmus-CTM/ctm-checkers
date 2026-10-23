# Trusted checklist recording checkpoint

`ctm_variants.bot` is a native-only planner, not an installed GitHub workflow.
It decodes explicit hidden identities from individual and per-question bulk checked lines, verifies same-repository
and authenticated own-bot-comment provenance, requires repository write permission,
checks exact current id/hash/number and explicit passing tests, and emits data-only
approvals with named failing exclusions for bulk actions. Already recorded approvals and overlapping bulk/individual ticks are idempotent. It never executes course code
or constructs shell commands. The caller must obtain provenance from GitHub and
verify the unprivileged records artifact belongs to the exact PR head, then use
leased manifest writes and a Git ref lease.

`ctm_variants.checklist` now supplies a pure per-question renderer and pending-tick
reconciliation. It lists only new/changed candidates; current approved/rejected
decisions are summarized without actionable boxes. Each candidate has its stable
decided number or an explicitly new label (never number zero), note, variable and
teacher values in GitHub maths, test verdict, actual producer-supplied preview URL
and a hidden identity. Changed values/answers show **was → now**, with unchanged
fields named explicitly. The first box approves all listed passing candidates;
the existing planner reports failed/unverified exclusions rather than approving
them.

The renderer flattens authored newlines/control characters and escapes note,
label, variable/teacher keys and mathematical delimiters so authored content
cannot introduce another checked row or hidden token. Preview links permit only
ordinary HTTP(S) URLs. Comment-size budgets fail explicitly, without truncation.
The previous comment must be authenticated by its caller as the bot's and carry
the same hidden question marker. Only exact pending id/hash/number identities
retain ticks, and only while their current test verdict is explicitly passing.
Gone/changed/recorded/nonpassing identities are reported as not carried.
Refreshing a checked bulk row expands its original identities into individual
checks and leaves the new bulk row unchecked; newly generated candidates never
inherit consent from the old bulk tick. Already recorded decisions lose boxes.

Focused pure contracts: `python -m unittest discover -s tests -p
test_variants_checklist.py` (8), plus the planner's 4 contracts. These tests perform
no GitHub IO or source execution. The pure renderer does not update a live comment
or claim the producer's preview-card routes exist; callers supply the actual URLs.
The trusted adapter/inactive serial workflow template and explicit check dispatch
are described in [the adapter checkpoint](variants-github-adapter.md).

The trusted producer and sticky-write adapters are now connected by a
comment-independent neutral artifact protocol and inactive workflow templates.
Source/fake tests exercise first comment creation, recording against its actual
marker and latest-body tick reconciliation; no actual comment was sent. See
[producer boundaries](variants-producer.md). Still required before day-one bot
completion: reviewed course installation/coverage/inventory, real preview
publishing, rejection commands (the disconnected page supports rejection),
retirement of comments for removed questions and the >30-question summary, and
observed proof that a dispatched check attaches to its new head. GitHub has no
joint comment/head transaction; snapshots are rechecked immediately before
updates. No workflow or privileged automation is activated; authoring remains
draft/HOLD.
