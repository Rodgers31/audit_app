# Privacy/callback decisions and safe acceptance — 3 November 2026

Status: **pending owner/provider evidence; no activation authority**. Source
baseline is `8f08d85a1b059b83d8b8a3823f5f06fd33eb4e39`, tree
`429c94692890811fcab68668c5ee1ecd19226c5e`. This document does not approve a
policy, install an attestation, authorize an export/deletion, or change a live
setting. Keep new/reconnect callback admission, native and automatic source admission,
and privacy execution held; publishing, uploads, workers and financial generation
must stay OFF throughout this work.
The release owner alone owns current deployment, ingestion pin and saved-grant
checks. No production observation is inferred from a local test image.

## Decisions already made, with their limits

[The owner's 22 October decision](https://github.com/Rodgers31/audit_app/issues/488#issuecomment-6330295479)
names **Roger as recovery custodian and seven days as the rolling retention
window for private local database exports**. It does not cover application
records, media, credential/digest/signing keyrings, provider backups, WAL,
traces, exports/drains or other provider/subprocessor copies. It grants no new
access and authorizes no disposal, key retirement or cleanup automation here.

[The B42 logical restore](https://github.com/Rodgers31/audit_app/issues/488#issuecomment-6332208730)
accepted an actual operation-scoped full logical database restore, including
its stated logical roles/permissions. Preserve that acceptance. Its stated
private archive deadline, **29 October 2026 at 02:45:54 UTC**, is now historical
and past. Roger must reconcile the actual current copy inventory and enforcement
without exposing archive contents: still present, disposed with evidence, or
unresolved. This lane did not inspect, extend retention for, or delete that
archive. B42 did not accept provider physical/WAL/control-plane recovery,
provider-held Vault keys, environment secrets, media payloads or independent
copy durability. A synthetic restore cannot refresh those production claims.

[Public notice acceptance](https://github.com/Rodgers31/audit_app/issues/488#issuecomment-6353678755)
is complete in its recorded scope. The existing 14-day response sentence is
not a newly approved erasure deadline. No new public copy or general legal
compliance determination is proposed.

## Exact remaining owner decisions

Every row below is **pending**, except the limited Roger/private-export decision
above. For each approved row the owner must record: named responsible person;
exact current/historical copy inventory and policy version; purpose and
applicable obligation/basis reviewed by the owner or adviser; retention trigger
and horizon; legal/evidence/uncertain-delivery exceptions; authorized disposition
and approver; completion evidence; restore cutoff/suppression and failure owner.
A token expiry, encryption setting or provider lifecycle default cannot fill in
these decisions.

| Decision | Scope and specific owner input required |
| --- | --- |
| Current and historical credentials / pending OAuth envelopes | Identify grant generations, flow status/expiry, revocation and leases, shared Page/User lineage, dependent key versions and backup references. Decide retention and disposal per class, including pending/uncertain work. |
| Account, ownership and privacy-request records | Include app namespaces, all digest versions, frozen receipt variants/status references, legacy/unattributed subjects and immutable ownership history. Decide accountable retention and subject handling. |
| Audit, delivery and financial provenance | Distinguish evidence necessary for accountability from attributed subject data. Decide purpose, exceptions, retention, access and verification without silently rewriting published evidence. |
| Application DB and provider copies | Name current database, scheduled backups, any actual WAL/PITR/control-plane copies and managed-key dependencies. Obtain provider scope/exception evidence. The private-local-export rule does not approve these. |
| Credential/digest/signing-key recovery copies | Name actual custodians, approved existing destinations, authorized access and an independent restore reviewer. Establish each retained generation's recovery dependencies, break-glass procedure and retirement prerequisites. Roger's recovery role alone does not establish independent custody. |
| External signed deletion ledger | Name signer/custodian and independent public-key witness. Establish authoritative inventory/cutoff, persistence/readback, access and suppression before restored grants can be used. No DB receipt is not proof that no external intent exists. |
| Hosting/security/error/trace/export copies | Assign provider-evidence collection and retention/access/export/disposal responsibility for each actual Render/Vercel/Meta/Supabase/subprocessor/exporter copy. Unknown internal collection remains unknown. |
| Private local exports | Roger confirms inventory, oldest copy and seven-day enforcement under the existing decision, including the historical B42 archive. No broader retention approval is required merely to acknowledge the already-decided limited rule. Any proposed exception needs its own explicit decision. |
| Media/object recovery | Storage lane owns the object/ledger/writer/lifecycle policy and acceptance. Coordinate the exact approved existing destination and responsible people there; this document supplies no media retention, upload or deletion authority. |

A decision record should say: “I approve [exact policy content/version and
category/copy inventory], with [named custodian and independent approver],
[trigger/horizon/exceptions], [completion and restore-suppression responsibility].
This [does/does not] authorize [explicit bounded action].” Leave unknown fields
pending. Do not install this draft's digest as an approved policy.

The implementation enforces correspondence, not the policy's legitimacy:
`backend/social/privacy/workflow_contracts.py:36` defines default-off workflow
configuration; `workflow.py:50` refuses disabled execution, `:54` requires the
installed policy pair, `:126` requires a configured independent approver, and
`:198` requires current approved scope/version plus custody before execution.
Even completed local erasure reports `request_completed=False` and explicitly
retains audit/delivery/ownership/financial/backup categories (`workflow.py:242`).
`restoration.py:13` validates signed intents against the supplied public key and
defaults to validation only; independent key provenance remains an operator
prerequisite. Neither result authorizes publication or claims full deletion.

## Provider evidence that remains necessary

This lane refreshed read-only issue snapshots for #488 and #767; they remained
open, last updated 22 and 27 October respectively. Those issue dates do not
establish support state. Preserve the 2 November private
`callback-privacy-20261102/REPORT.md` and `PROVIDER_OBSERVATIONS.md` as historical.

**A human Render answer has now been received.** During the 3 November release,
the parent captured Jérémy's reply in
`release-893-897-20261103/render-deploy-start.txt`. He confirms that the public
docs cover customer-visible logs and Hobby generates no customer HTTP request
logs. He explicitly leaves internal infrastructure/subprocessor raw-query copies
unverified and cannot confirm internal retention, access or pre-ingestion
redaction for this plan. This supersedes the prior *human answer pending*
description of [the existing escalation](https://github.com/Rodgers31/audit_app/issues/767#issuecomment-6447207800),
without closing any internal-copy boundary. No vendor reply or setting change
was made or authorized.

The missing evidence is an authoritative provider contract for the **existing
workspace/service and exact callback path**, identifying:

- Internal edge/proxy/CDN, security/abuse, trace, diagnostic/error and
  subprocessor collection, including raw and decoded query values.
- Whether supported omission occurs before every retained copy while preserving
  handler delivery; exact supported setting, scope and failure/security exceptions.
- Retention, authorized access, exports/drains and downstream copies, owner
  prevention, historical deletion limitations and unverifiable categories.
- Launch POST bodies/nonces, cookies and Authorization/header handling as well
  as success, denial/error and malformed callback queries.

No follow-up is sent or queued by this document. Use the existing conversation
only after explicit authorization; no duplicate case, vendor message, paid
investigation, project access, setting or new resource is authorized here.

The existing Vercel human answer offers **no documented selective early query
omission preserving delivery**. Case closure is not privacy acceptance. Treat
that transport option as unsupported on the supplied evidence. Application
scrubbing, Sentry filtering, Uvicorn filtering, short token lifetime and downstream
drain filtering cannot prove omission before an upstream copy. An empty log or
no configured customer stream is not noncollection evidence. Fixture redaction
proves only the instrumented local emitter.

The implemented direct Render callback can avoid the Vercel callback leg only
when the actual route bypasses it. It still reaches Render's earliest collectors.
`backend/social/connections/config.py:91` separately requires exact direct
configuration and callback qualification. Never add a verified callback URL
merely to enable the UI. A generic fragment/form_post/SDK redesign has no accepted
equivalent contract for this owned Meta success/denial/error flow. No new service,
relay, plan, permission or login scope is proposed.

## Bounded acceptance plan after decisions, without activation now

1. **Bind the proposed scope.** The owner approves exact policy content/copies,
   people, current existing destination, ledger cutoff and permitted action.
   Reconcile the storage lane's separate decisions. Preserve previously accepted
   logical restore, key/subject recovery and public-notice evidence at their
   original scope; acquire only genuinely missing current evidence.
2. **Resolve the earliest collector.** Retain the provider answer/configuration
   contract and exact URL, deployed source/build, registered redirect set,
   API/admin origins, DNS/proxy/redirect chain, current workspace/compute plans,
   actual log/security/trace/exporter/subprocessor inventory and exception scope.
   Require supported omission before retained copies, or a separately reviewed
   transport that avoids the sensitive URL surface. Unknown earliest collectors
   or missing technical qualification leave `CALLBACK_INGRESS_UNVERIFIED`.
   Owner approval of retained-copy policy cannot substitute for this technical
   requirement or clear the hold by itself.
   The attestation validates exact set equality (`callback_ingress.py:27`); it
   neither redacts nor automatically expires when an unmeasured host changes.
3. **Request a separate bounded qualification allowance.** Only after the first
   two steps, an authorized operator may propose inert correlated markers with
   positive method/status/request witnesses across success, denial, encoded and
   decoded duplicates, oversized/invalid inputs, early failure/rate limits,
   slash paths, launch body/cookie/header surfaces and all relevant collectors.
   Zero visible entries, sampling or a dropped request is insufficient. No such
   production callback canary or login is authorized by this document.
4. **Prove application and restore boundaries locally.** Bind source and fixture
   identity; preserve state/actor/session/browser binding, exact origins/targets,
   encrypted staging, one-use consumption, expiry/replay/uncertainty refusal,
   independent signed-intent inventory/cutoff and restart/persistence failures.
   Exercise normal and optimized Python for any changed acceptance/verdict code,
   with two independent executable reviews. Fake-provider tests cannot attest
   provider storage, revocation, retention or real erasure.
5. **Return an exact reviewable production proposal.** Keep all controls off.
   An attestation/redirect/configuration change, real owned-provider HTTPS/cookie/
   opener/denial/selection check, export/erasure/suppression apply, upload, worker
   or send each needs its applicable explicit authority and completed prerequisites.
   Preserve original failed receipts and unknown outcomes. A partial local
   completion must remain partial; no retry may silently create duplicate effects.

Existing saved-grant maintenance does not enter new OAuth and belongs to the
release owner. This callback hold supplies neither an extra reconnect requirement
nor a saved-grant acceptance stamp. Ordinary-auth/recovery hosting query and
cookie surfaces also retain their separately documented provider boundaries;
qualifying a direct Meta callback would not qualify those Vercel routes.

## Local launch-body review disposition

The initial isolated-router hypothesis omitted a mandatory serving boundary:
`backend/main.py:1934` calls `install_security`, and `:1943` adds the outer
`SocialNoStoreMiddleware`. `middleware/security.py:265` installs
`RequestResourceMiddleware`; that middleware applies the body deadline before
route dispatch (`middleware/request_resources.py:286`) and releases admission in
its finalizer. The route's own 1,024-byte cap is not the earliest buffering cap:
the outer default is 32 MiB and a ten-second body deadline. Host/edge transport
bounds and deployment qualification remain separate; no smaller upstream cap
or DDoS guarantee is claimed.

No product defect was established, so `direct_api.py` is unchanged. The new
`test_direct_launch_body_boundary.py` exercises the actual security installer and
private-response ordering with an inert provider seam and a compressed fixture
body deadline. The injected held error tests route propagation only; actual
malformed/stale attestation behavior is exercised by the existing
`test_callback_ingress.py` cohort. Router-only watchdog failures are retained as rejected-composition
controls, not a pre-fix production vulnerability. The tests cannot prove provider
collector noncollection, production configuration, distributed quotas or callback
activation readiness.
