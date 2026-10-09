# Independent Spec review

Reviewed source: `856176512b470e37d6df55c7c8c545820db69b15`; pinned base: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`; helper blob: `674a7c7c8ca3ca4c27c9cefce7e50bc6659d9a7b`.

Diff: `git diff f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d...856176512b470e37d6df55c7c8c545820db69b15`. Origin: actual current issue #567, parent #545, frozen Batch 7 SPEC.md and dispatch-contract-examples.json.

**Findings: 0 missing/partial implementation requirements, 0 scope-creep findings, 0 incorrectly implemented requirements.**

The pinned caller inventory supports retention of the public compatibility helper. Required authentication takes precedence after case-insensitive per-call header collapsing; Prefer is emitted once. The HTTPX auth override rejection directly protects that requirement and has a zero-transport regression. Response handling confirms exactly one matching id/roles row, rejects absent/malformed/mismatched or failure-marked acknowledgments, preserves empty-list 404, and propagates upstream/transport failures without claiming role success. Count is unchanged and tested through actual transport. Active Users routes/provider/authentication remain read-only.

I inspected the old-code receipt: the public role helper raises duplicate-keyword TypeError with `requests=[]`; two count controls pass. I independently replayed all 68 new helper/import cases and 164 retained Users controls: **232 passed, 2 existing SQLAlchemy deprecation warnings in 3.24s**. Both import subprocesses execute shared role/count, signed-auth lookup and active provider through actual MockTransport; the replay additionally blocks socket.connect globally. Exact command and output are in `spec-test-command.txt` and `spec-test-replay.txt`. Clean environment, dotenv disabled, absolute owned backend PYTHONPATH, synthetic .invalid provider/JWT values, read-only Python runtime; no servers, external requests, live database or installation. Reviewer pytest temporary resources were removed.

Delivery limit: lane handoff, final evidence manifest, issue accounting and draft PR were still being assembled when this source review ran; their final completeness is not certified here. Hosted/security/quality gates and deployed behavior are unexecuted. Pre-existing diagnostic/query/read-helper issues remain outside this bounded acceptance and must retain follow-up accounting. This is compatibility maintenance, not a current Users blocker.
