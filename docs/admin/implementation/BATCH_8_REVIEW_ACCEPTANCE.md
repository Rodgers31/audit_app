# Batch 8 coordinator review and acceptance

Review baseline: `97fe77462b4e63ffad7dc393b8bf97d3e51571f7`.
This records code acceptance before GitHub publication/merge. Current PR/issue
state is authoritative on GitHub. The complete combined candidate includes
PR #584, which remains held; these checks do not assert production deployment
or that #584 is part of merged main.

| Delivery | Coordinator result | Scoped reviewed tip |
|---|---|---|
| #578 producer closure | Accepted for merge; fresh SQLite receipt directory fixed | `f0b20d696bf65540e0818baff9b9cda98ea14224` |
| #579 legacy helper | Accepted for merge; diagnostics premise refuted, typo/test isolation fixed | `97dcdb5bbdc9d3d06ee8a31ad90a45d7ea768937` |
| #580 developer dependencies | Accepted for merge; engines/report versions/filename references repaired | commit containing this brief |
| #584 native exclusion, completed by Claude | Code fixes verified; keep draft pending #583 | `9e97ca3f1ca43f103a8655447a86d889456a218a` |

The original Codex native author was service-blocked. Claude continued the
preserved work and opened #584. Its committed handoff, evidence and GitHub
history were reviewed; the private Claude session URL required sign-in and
could not be read. The three other author sessions completed normally.

## Review dispositions

All eight inline findings and the full review bodies were evaluated. Six
inline findings required code/docs changes. The HTTPX inheritance premise was
refuted on actual supported 0.25.2 and installed 0.28.1: InvalidURL derives from
Exception, not HTTPError; malformed URL stays bounded 500 before transport,
while ConnectError stays bounded 503. Restart retention is intentional under
#572's no-expiry-reclaim policy; replacement fences the stale adapter before
entry. #583 owns explicit reconciliation.

The two additional dependency review-body concerns were handled: actual
semantic versions are validated, and three historical evidence references have
a dated correction map. Historical reports/receipts remain preserved.

For #584, JSON string "true" cannot count as a boolean refusal; RUNNING tags
must resolve to an active same-domain claim. Acknowledgement uses a savepoint on
the connection holding the continuity lock and commits that outer transaction.
Actual backend termination before commit retains ownership. Rejected receipts
preserve the lock so a later valid receipt can succeed.

One newly uncovered test defect was repaired: the signed-auth negative fixture
now scopes its own inert JWT verification key. It passes independently with
absent and different ambient keys; application authentication is unchanged.
The retained PDF acceptance workflow still deliberately pins the older script
hash, so a separately reviewed pin rebind is required before a future authorized
invocation. No workflow/provider/storage operation was run.

## Executed verification

- Combined candidate: **1,425 selected backend passes, 3 explicit retained-PDF
  prerequisite skips**. The initial eight failures are retained: five exposed
  the JWT fixture defect; the other three were missing warmup configuration,
  owned lint target and Git metadata in the coordinator's copied fixture.
- Frontend: **147 suites / 2,077 passes**, one existing optional financial skip;
  production build, full lint/types, tree and engine-strict lock checks pass.
- Dependency controls: **29 pass on macOS and pinned Linux amd64 emulation**.
  Real image/ZIP/native CPU inference and browser WASM/fallback ranking pass.
  The two browser contexts have zero unexpected requests/page errors.
- **173 baseline production lock records remain byte-identical**. Production
  audit is zero; full audit still has 26 macOS / 27 Linux entries at the same
  two advisory roots. #494 remains open.
- Exclusion/process/migration selection: **197 passes**, no skips/xfails.
  Actual PostgreSQL acknowledgement controls also pass on minimum SQLAlchemy
  2.0.23 with Python 3.12 and installed 2.0.46 with Python 3.13.
- Independent Standards: no remaining hard finding or actionable smell.
  Independent Spec: no new code defect or scope creep; tracked writer and
  operational acceptance limitations remain. Independent behavior: **64/64**
  executed controls. Failed probe/setup attempts remain separately recorded.

These selections overlap; their counts must not be added. The broader combined
selection includes the held exclusion implementation. Source/evidence hashes
and exact invocations are retained under the coordinator `BATCH_8_REVIEW`
artifact directory and the four committed delivery packets.

## Remaining work

Keep #572/#554/#545 open while #584 is held. #581 tracks legacy ETL writers
outside the shared claim; #582 tracks boot/weekly bootstrap writers. #583
requires a production RUNNING census, actual pooler idle-cutoff evidence and a
reviewed audited reconciliation path, with quiescence across every writer.
None was certified here. Dedicated dispatch stays default-off and only the
accepted OAG-to-audits mapping is implemented; five mappings remain pending.

Recommended independent lanes: #581 legacy writers; #582 bootstrap ownership;
#583 reconciliation implementation/local proof and operational evidence plan;
#494 residual tooling remediation. The PDF workflow pin follow-up is a smaller
maintenance task before its next separately authorized run. Deployed telemetry
(#525), Meta authorization/custody (#488), storage/reconciliation (#490) and
hosting/egress prerequisites (#476/#481) also remain open.

Actions was read back disabled. Hosted quality/security checks and production
acceptance are unexecuted. No policies, fabricated statuses, bot-review request,
production migration or live financial/provider/publication write were used.
The dirty primary checkout and shared runtimes remained read-only.
