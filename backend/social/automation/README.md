# Dormant selective policy authority

This extends PR704 on its exact head2f3b36e2749a48dbe7d93f001081ddc756a61412.
It implements blueprint sections15/16 and phase10 without enabling rollout.
`SOCIAL_POLICY_AUTOMATION_ENABLED` must be exactly `true` (default absent/off),
and independent database approval/schedule/publish controls default false.
Global/account publication controls and media uploads are never enabled here.
No new service, scanning scheduler, provider integration or paid dependency exists.

The existing committed-event `consume_observation` invokes the policy path only
when its ceiling and automatic approval control permit it. An understood refusal
rolls back the nested policy work, preserves the pending human draft and records
`automation.human_review_required`. Unexpected runtime/storage failures propagate
and roll back the source transaction. Existing post-commit caller integration
and real qualified source data remain dependencies of the event boundary.

## Durable authority and operator ports

All endpoints use the existing admin authentication, private/no-store responses,
strict inputs, command idempotency and atomic audit/receipt transaction.

1. Existing `/automation/rules/{id}/versions` remains disabled/shadow only.
2. `POST /automation/operating-evidence` records explicit human accuracy,
   reliability and correction-review acceptance, an external evidence URL/hash,
   and1–100 exact would-allow shadow decisions. Each must match an existing
   human-authorized exact revision/hash whose selected targets have confirmed
   published outcomes. Missing outcomes cannot produce acceptance. This is a
   human attestation port, not an external report downloader or an automated
   claim that a representative pilot passed. Tests use visibly synthetic outcomes;
   no real operating acceptance is shipped or seeded.
3. `POST /automation/policy-snapshots` independently authorizes an immutable copy
   of the current exact rule/hash, accepted evidence/hash, and approved source
   scopes, with at most30days validity. A bare rule is insufficient. Later rule
   versions invalidate older authority; snapshot bytes/history remain unchanged.
4. `PATCH /automation/policy-controls` selects that snapshot and changes the
   three hierarchical controls with expected version and reason. Enabling any
   control requires the environment ceiling. This endpoint does not change
   global/account publishing, source qualification, uploads or provider access.
5. `POST /posts/{id}/policy-authorize` requires exact version/revision/hash and
   snapshot ID. It records an immutable decision then creates publication and
   frozen targets through SocialService's shared authorization implementation.
6. `POST /posts/{id}/policy-schedule` rechecks current authority and queues the
   frozen targets through the same shared queue implementation as human posts.
   `GET /automation/policy-controls` and paginated `/automation/policy-decisions`
   expose effective ceiling/raw controls and exact decision inputs. These are
   operator APIs; there is no browser activation toggle. Existing UI handles
   nullable human identity and labels policy authorization; manual scheduling
   controls cannot reuse that authority. Editing/duplicating creates a draft
   needing new authorization. Cancellation preserves immutable reservations.

## Gates and ordering

Initial policy scope is a deterministic single-actual-fact dataset announcement.
The approved sample freezes source key/type, title, entity, fact/metric/period,
comparison, unit/scale, publisher, document locator/URL and canonical destination.
The snapshot also freezes a positive exact-decimal minimum absolute change in
that approved fact scale (default1). A previous event with the same approved
semantics is required; bootstrap/backfill and subthreshold changes retain human
review. A document-only change cannot masquerade as material financial change.
Different semantics, edits/overrides/media/hashtags, pending corrections,
allegations, contested/reputational claims and financial-claim categories retain
human review. This does not claim a text classifier can detect arbitrary claims;
only an exact previously human-reviewed neutral source/template scope is eligible.
Facts are reread from the immutable source event and current cursor, with exact
fingerprint/provenance/hash/template checks and at most24h verified freshness.
Qualification of underlying publisher rows remains the source producer's contract;
this module does not independently fetch publisher documents at dispatch.

Authorization and scheduling validate current global/platform/account controls,
capability/permissions/adapter/format and capability-check age (at most24h).
Only free operation classes are eligible here. X remains refused, including zero
budget. Paid reservations are not invented; peer platform code is not imported.
TikTok additionally requires explicit human acceptance of its exact API product
for unattended use plus a supported unattended capability. This grants no product
access and is separate from ordinary authenticated account connectivity.

The global SocialControls ordering lock serializes policy selection, rule
supersession, source supersession, authorization/reservations and worker permits.
Rule/source writers retain their existing generation-control-before-global order;
policy/worker paths never take the generation lock. Account locks remain ordered.
The worker's existing mutation admission invokes fresh policy authority and target
validation in its lock-holding transaction, before any external mutation. Read-only
reconciliation remains independent. It rechecks the ceiling, all automatic controls,
active/current policy, snapshot/evidence integrity and expiry, exact revision/hash,
current source/capability/account/budget gates and frozen payload identity.

Cadence reserves at most1–3 automated posts/account/rolling24h, with60–1440min
spacing across rules, all selected accounts and cancellations. Bounded immutable
decisions make reservations survive restart. Both past and future rolling windows
are checked. Scheduling preserves the approved reservation (at most5min lateness),
never shifts into another slot, and refuses outside content/policy validity. Final
public permit admission also checks actual prior policy submission/publication times,
so processing delays cannot compress public submissions into an unsafe cadence.

Migration a706b15a0001 is additive after a704b15a0001, with private/RLS tables,
immutable history triggers, a composite exact-authority FK and an additional
immutable publication-decision-link guard. No policy rows or activation are seeded.
Downgrade refuses durable policy publications or active automatic controls. The
worker role contract describes only additional read access and trigger integrity;
no role/grant installation or production migration is performed. Existing deployed
worker privileges therefore require separate qualification before any activation.
Root must serialize the complete sibling migration chain and replay its exact tree.

## Acceptance limits

Local SQLite/PostgreSQL/HTTP/fake-boundary/Chrome evidence is recorded in HANDOFF.
None is a deployed/live pilot or accepted operating evidence. Publishing/uploads
remain off. Genuine shadow-versus-human operating acceptance, production source and
worker-role qualification, provider eligibility, cost/capacity/retention/custody
acceptance and a separately authorized narrow live rollout remain open. Broader
source/format/category expansion is outside this conservative initial policy scope.
