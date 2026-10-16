# Batch15 rendering and analytics candidate

This is a local implementation candidate, not deployed or live accepted. Publishing/uploads remain off. Accepted starting commit: `06896185005d822c4b29888138b984510dd1fdbd`. Checkout: `/Users/roger/.codex/worktrees/b15-rendering/audit_app`; branch: `codex/b15-rendering`. The final head/PR and cleanup readbacks are recorded in the coordinator packet's `lane/rendering-status.md` (written after the delivery commit to avoid a self-referential commit hash).

## Implemented

- `backend/social/studio/`: six immutable version1 fact-card templates with required factual roles/default target formats/layout references. Compositions cite an existing immutable source revision's evidence, reject unresolved placeholders and unsafe/nonprintable text, and bind the actual source/input hashes.
- Durable local render queue; one global local renderer, immutable input/derivative/approval evidence, cancellation, retained interrupted ownership and explicit recovery after180s. Explicit retry creates a fresh job/directory, at most two attempts, without inherited approval. No renderer runs in the delivery worker or web scheduler.
- Actual Pillow PNG and FFmpeg H.264720×1280/24fps video,15–45s. Burned-in card captions, fact IDs, timed transcript and downloadable SRT sidecar. Voiceover absent. No remote input paths, filters, templates, AI/TTS or external compute. FFmpeg file/pipe whitelist, single encoding thread,120s watchdog, CPU/file/descriptor limits,512MiB aggregate sampled RSS guard (200ms; not a hard macOS memory sandbox), additional Linux address-space bound. Retained inventory capped20jobs; no automatic byte deletion.
- Authenticated no-store list/preview/captions/review/cancel/retry/attach APIs. Preview hashes exact served bytes. Approval requires exact inspected checksum/current source and explicit fact/source attestation. Attach accepts only the existing inspected media asset with that checksum and creates a new normal draft revision. It never uploads or authorizes publication.
- Typed `MetricsPort`/`MetricRequest` fixture seam, bounded separate spawned-process reads, durable quota reservations before reads, one account read/hour and24/day,20records/32KiB/10s per read. X always refuses under zero spend. Failures retain reservations. Provider name/API version/unit/period/window/collection/freshness and unavailable reasons remain distinct; zero stays zero. There is deliberately no native provider transport registration or automatic collector/scheduler.
- Current admin design retained: `/admin/social/studio` with template/source form, queue, checksum preview/approval, caption download and matching-media attachment, calendar with approved timezone and cancellation/revocation history, provider-semantic analytics with dynamic stale state. Navigation wired from existing review workspace.

## Verification and reviews

Evidence root: `/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/lane/rendering-evidence`.

- `local-final-v1/receipt.json`: source-bound authored cohort34passed including3owned PostgreSQL cases. Exact argv, interpreter, input hashes and raw stdout/stderr retained. Recorder: `backend/scripts/social_studio_acceptance.py` with generator hash/readback.
- `standards-final-execution-v1.json` / `standards-final-review.md`: independent34normal +34optimized, zero skips; forced real SQLite approval/edit interleaving and13hostile frontend contract cases. No unresolved findings.
- `spec-followup-final.json` / `spec-review-followup.md`: independent34backend +28normal/28optimized adverse probes; provider-error redaction;12actual decoder controls +8Jest tests. No unresolved findings. Earlier findings and failed/source-drift receipts remain historical, not relabelled.
- Confirmed red→green: persisted input mutation, SQLite quota race, retained metrics descendants, SQLite approval/edit race, malformed ready DTO and expired analytics freshness. Initial author failures also retained in `initial-red.log`/source hashes.
- Full Alembic chain replayed on fresh owned PostgreSQL17 from empty DB through candidate `a705b15a0001`: `migration-full-final-v1.log`. Three real PostgreSQL tests cover concurrent enqueue/metrics quota, actual render/review, RLS/no PUBLIC grant, SQL history immutability and retained-history downgrade refusal. This does not certify integration with peer candidate migrations.
- Frontend Jest:8passed. Full project tsc reports the pre-existing `components/map/StyledGeography.tsx:36` style-type error only (`typescript-final-v1.log`). No unrelated fix made.
- Chrome local contract fixture: source selection, required facts, queue/cancel, exact-PNG hash preview then attested approval, disabled attachment with uploads off, provider0/unavailable/stale states, calendar timezone/history,390px no horizontal overflow and labelled controls. Screenshots: `browser-v1/studio-desktop.png`, `studio-mobile.png`. Browser responses are fixtures; this is not provider/live render completion proof. Fixture reused installed Next15.5.20 runtime, while repository package target is15.5.27; no install performed. Full locked frontend build remains unverified.

Reproduce authored local cohort using the existing interpreter (no install):

```sh
PYTHONPATH=backend /Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/ENGINEERING_BATCH_14/worker/venv/bin/python backend/scripts/social_studio_acceptance.py --output /absolute/fresh/evidence-directory
```

Add `--optimized`; add `--postgres` only after provisioning this lane's owned `127.0.0.1:55402/b15_rendering_final` fixture and applying the complete chain. No production DSN is accepted by the PG tests.

## Runtime and integration

API configuration is default off (`SOCIAL_STUDIO_ENABLED=false`). Explicit local configuration requires an existing owned0700 absolute root with no symlink ancestors, absolute FFmpeg/ffprobe paths and verified spare capacity. `configure_studio` performs no provisioning. No credentials or native adapters are implicitly loaded.

```sh
SOCIAL_STUDIO_ENABLED=true
SOCIAL_STUDIO_ROOT=/absolute/owned/private/render-root
SOCIAL_STUDIO_FFMPEG=/absolute/path/to/ffmpeg
SOCIAL_STUDIO_FFPROBE=/absolute/path/to/ffprobe
```

After a separately authorized local/API setup queues a job, the separate one-shot operator is:

```sh
python backend/social_studio.py render JOB_UUID --enable-local-rendering --root /absolute/owned/private/render-root --ffmpeg /absolute/path/to/ffmpeg --ffprobe /absolute/path/to/ffprobe
```

The same explicit arguments with `recover` mark an interrupted job failed only after the bounded execution/reap window; they never clear its token/history or automatically retry. Normal and optimized Python guard executions are in the independent reports. Never point this command at production without coordinator qualification.

Metrics integration uses `social.studio.analytics.collect(factory,target_id,ports,enabled=True)` from a separate explicit operator process. The platform lane must supply an importable/pickleable authorized zero-cost port for its own platform, respecting the request contract. Default enabled isFalse, empty registry is unavailable, X remains blocked. No unmerged platform source is assumed. Collection storage/read APIs are implemented; live/native transport binding remains code integration work, not proof supplied by fixture data.

Shared edits: `backend/main.py` imports/registers studio router and default-off runtime; `backend/social/__init__.py` registers additive models; `frontend/components/admin/social/SocialWorkspace.tsx` adds studio navigation. No package/lock/role-contract or existing media/worker module edits.

Migration reservation: `a705b15a0001`, candidate down_revision `a545b14a0001`. Coordinator must serialize its predecessor after recovery→media→generation→platform candidates, review exact resulting diff and replay whole integrated chain before any migration lands. No worker grants added; new tables enable RLS and revoke PUBLIC/anon/authenticated access.

## Remaining original requirements and gates

Local rendering, persistence, APIs and admin views are implemented/tested. Native provider metrics transports/credential/read-scope and product-window binding are not registered here; authorized platform integration and real-provider fixture acceptance remain. Rendering runs only by explicit local operator; no hosted worker/scheduler is added. Existing media intake/storage must be separately accepted/enabled before reviewed bytes can become a real ready stored asset for TikTok/Reels. Uploads remain off. Exact-checksum attachment/new draft review is implemented and fixture-tested, but no provider video upload/publication was performed.

Production migration/deployment, verified existing spare CPU/RAM/disk capacity, storage/retention/custody, actual provider permissions, X budget and TikTok access/origin/product eligibility remain coordinator-owned external/live gates. No production Chrome/cloud/credentials, deletion, publication, upload, paid review or Actions dispatch occurred. 12ui hosted image generation was not used because the human's no-cost/no-external-AI constraint overrides that workflow; current UI styling was reused. WCAG conformance and assistive-technology acceptance are not claimed.
