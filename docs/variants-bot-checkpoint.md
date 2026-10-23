# Trusted checklist recording checkpoint

`ctm_variants.bot` is a native-only planner, not an installed GitHub workflow.
It decodes explicit hidden identities from individual and per-question bulk checked lines, verifies same-repository
and authenticated own-bot-comment provenance, requires repository write permission,
checks exact current id/hash/number and explicit passing tests, and emits data-only
approvals with named failing exclusions for bulk actions. Already recorded approvals and overlapping bulk/individual ticks are idempotent. It never executes course code
or constructs shell commands. The caller must obtain provenance from GitHub and
verify the unprivileged records artifact belongs to the exact PR head, then use
leased manifest writes and a Git ref lease.

Still required before day-one bot completion: rejection commands, sticky preview reconciliation that
preserves unrecorded ticks, trusted-base GitHub adapter with permission and no-fork
checks, per-PR serial workflow, explicit check dispatch and proof that its status
attaches to the new head. No workflow or privileged automation is activated here.
