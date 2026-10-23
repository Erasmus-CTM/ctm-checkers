# Native disconnected review checkpoint

The native `ctm-variants.py --html` document now starts with a candidate overview
and defaults to undecided/changed rows. Each row shows its stable decided number
(or an explicitly new candidate label), note, canonical teacher input notation,
and actual recorded test verdict. Details expose the component-resolved student
Markdown, worked solution, variables and test report as escaped text. Changed
rows compare retained snapshot values and teacher answers as **was → now**;
unchanged fields are dimmed.

Individual decisions, **Approve all passing variants of this question** and
**Approve again: changed, answers unchanged** stage choices in memory. Bulk
approval preserves existing/staged rejections and names candidates without a
passing test result. **Undo last staged action** restores the preceding staged
batch. Failed or unverified candidates cannot be approved through these controls.

**Download decision request** exports one `decide-many` JSON request containing
the original `baseHash`, resolved records and all staged decisions. Project root
and manifest path are explicit inputs. Apply with the native CLI, then regenerate
the review. The existing native writer validates the whole batch before one
atomic leased write and rejects a reused/stale request. The page never claims to
save files; reload discards staged choices.

Focused verification: `python -m unittest discover -s tests -p
test_variants_review.py` and `NODE_PATH=<Playwright node_modules> node
tests/variants-review-browser.cjs`. The Chromium browser check exercises keyboard
bulk approval/undo, escaped previews, changed snapshots, rejection retention,
excluded failing/untested candidates, download contents, real native batch apply
and stale-write rejection. It uses a local byte-preserving HTTP server and no
browser Python or CDN.

This is the native disconnected seam. It does not supply full filter-rendered
multilingual student cards, live Try it/Check, a connected save helper, project
scanning, or course review-profile integration. Those require the component and
shared review producers; this document labels its previews as resolved text.
