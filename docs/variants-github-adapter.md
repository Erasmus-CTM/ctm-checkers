# Trusted-base GitHub adapter checkpoint

This is an **inactive template and fake-transport-tested adapter**, not an
installed bot. No live comments, decision commits or workflow dispatches were
sent to test it. Day-one bot completion still needs the real trusted records
producer/artifact workflow, sticky comment/rejection integration, and observation
that the explicitly dispatched check attaches to its new commit.

The privileged native launcher is `ctm-variants-bot.py`, included by the canonical
native-only producer. It runs from a trusted default-branch checkout with isolated
Python imports. It never checks out, imports or executes PR course code. Its REST
transport bounds response/archive sizes and strips the bearer token on approved
HTTPS artifact redirects. Tokens are not printed.

Before recording, it obtains the event sender's repository write permission,
fetches the current own-bot comment, checks that it belongs to the PR, and rejects
forks, closed PRs and default-branch writes. It fetches the current branch head
from GitHub instead of trusting event or artifact claims. The mandatory trusted
producer inventory is read from the default checkout, never from artifact data.
Every listed producer blob must match between the exact PR head and the observed
trusted default-branch SHA, and that comparison is repeated before recording.

The reviewed inventory must enumerate the complete producer closure: workflow,
records entrypoint, native manifests, installers/bootstrap, scripts and imported
helpers, build configuration, locks and pins. The future unprivileged records
workflow must execute its producer from an exact trusted base SHA, not a PR's
replacement pipeline; it reads authored source from the PR. Variables and custom
checkers retain the approved Quarto author-code trust model and run unprivileged.
This work introduces no new OS sandbox policy.

The adapter accepts only a completed exact-head `pull_request` run of
`.github/workflows/variants.yml`, with the matching repository/PR and a successful
`variants-records` job. The overall run may fail the zero-approved publication
gate. It requires one nonexpired `ctm-variants-records` artifact, verifies the
GitHub archive SHA256 digest and reads one bounded `variants-records.json` member
without extracting paths. Its envelope is:

```json
{"version":1,"headSha":"<PR head>","producerSha":"<trusted producer SHA>","runId":123,"repositoryId":456,"pullRequest":7,"questions":[{"label":"q","path":"_variants/q.yml","commentId":789,"baseHash":"<current manifest digest or null>","manifest":{},"records":[]}]}
```

Only canonical `_variants/<label>.yml` paths are writable. The native format is
UTF-8 JSON, a YAML subset; general YAML is not interpreted by this adapter.
Artifact histories may append proposals but cannot alter the exact-head manifest's
old proposals, decisions or events. Current id/hash/number tokens and explicitly
passing tests are validated before the shared pure decision API is called.

The only branch mutation is GraphQL `createCommitOnBranch` with
`expectedHeadOid`; a concurrent branch move fails atomically. PR/producer heads
are rechecked beforehand, and the resulting head is checked again before the
explicit `variants.yml` dispatch, whose inputs include `expected_head` and the PR
number. The receiving workflow must declare these inputs and fail if its observed
head differs. Dispatch creation alone is not proof of check-status attachment.
The current comment identity, body and update timestamp are reread immediately
before the CAS; changed intent fails without recording. GitHub provides no joint
atomic operation for a comment edit and branch commit, so a later comment edit
cannot retroactively cancel a successful recording.

`templates/variants-decide.yml` is kept outside `.github/workflows`; it does not
activate automation. It uses per-PR serialization, pinned actions, default-branch
code, and event-file parsing rather than interpolating comment text into shell
commands. Install it only with the actual reviewed records workflow/inventory.

Focused tests: `python -m unittest discover -s tests -p
test_variants_github_bot.py`; planner tests remain in `test_variants_bot.py`.
The fake transport covers own-comment/write-permission/no-fork checks, producer
and run substitution, artifact digest/provenance/path/manifest faults, archive
path rejection, before-write head changes, a race inside the atomic CAS, and the
exact downstream dispatch. No API request in these tests leaves the process.
