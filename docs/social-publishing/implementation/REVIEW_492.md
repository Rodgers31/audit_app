# PR #492 review receipt

Reviewed integration HEAD `307f594eb4baffac56d7e050c30133e026333d4c` on
`codex/social-private-media-intake`, in the integration worktree, on 2026-10-03
(America/Chicago). The original feature worktree remained frozen.

## Dispositions

- **Valid:** [DEL filename comment 4175476915](https://github.com/Rodgers31/audit_app/pull/492#discussion_r4175476915),
  thread `PRRT_kwDOPmNsm86otNuT`. Before the fix, `UploadIntent` accepted DEL and
  the actual HTTP upload route returned 201 with a pending grant, while the
  frontend decoder rejected that filename. The server now rejects every C0
  character and DEL. Executed HTTP regressions assert 422/`INVALID_REQUEST`,
  private/no-store, zero asset/upload/budget/audit rows, and zero storage calls.
  Ordinary spaces, dotted names, and Unicode names remain accepted.
- **Half-right / clarified:** [body-only review 5403538086](https://github.com/Rodgers31/audit_app/pull/492#pullrequestreview-5403538086)
  names an availability-message concern without a second inline explanation.
  The existing MP4 conditional was already truthful: both all-format and
  image-only UI cases passed before changes. However, the UI always advertised
  JPEG/PNG, even when the server correctly advertised only MP4. It also kept
  accepting file selection after an open panel lost upload capability. Image
  labels now follow the exact allowed formats; unavailable panels show the
  server reason or a fallback and disable upload inputs and the upload action.
  Existing server capability computation and client response validation were
  verified and required no changes.

## Executed red evidence

Run from the integration worktree root:

```sh
PYTHONPATH=backend /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest -q --confcutdir=backend/tests/social backend/tests/social/test_media_review_492.py
```

Before source changes: **2 failed, 74 passed**. The two failures were DEL
acceptance in the direct contract and HTTP route (201 instead of 422).

Run from `frontend`:

```sh
./node_modules/.bin/jest --runInBand --no-cache __tests__/admin/social/media-review-492.test.tsx
```

Before source changes: **5 failed, 43 passed**. Failures covered JPEG-only,
PNG-only, video-only, capability loss with a selected file, and unavailable
fallback copy. The unchanged video conditional, all 33 client control-character
rejections, and eight malformed-capability cases already passed.

## Executed green evidence

Run from the integration worktree root:

```sh
PYTHONPATH=backend /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest -q --confcutdir=backend/tests/social backend/tests/social/test_media_review_492.py backend/tests/social/test_media_api.py backend/tests/social/test_media_config.py backend/tests/social/test_media_service.py backend/tests/social/test_media_integration.py
```

**124 passed**; two existing SQLAlchemy declarative-base deprecation warnings.

Run from `frontend`:

```sh
./node_modules/.bin/jest --runInBand --no-cache __tests__/admin/social/media-review-492.test.tsx __tests__/admin/social/media-ui.test.tsx __tests__/admin/social/media-parsers.adversarial.test.ts __tests__/admin/social/composer-media-integration.test.tsx
./node_modules/.bin/tsc --noEmit --incremental false
./node_modules/.bin/next lint --file components/admin/social/media/MediaUpload.tsx --file __tests__/admin/social/media-review-492.test.tsx
```

**142 passed in 4 suites**; TypeScript exited 0; lint reported no warnings or
errors (the command printed its existing Next.js deprecation notice).

## Boundaries

Checks execute actual validators, API handlers, capability probes, decoders, and
mounted components. Tests use isolated SQLite, explicit fake object storage,
actual Pillow availability, simulated Pillow absence, and a temporary local
ffprobe version fixture for the capability probe. That fixture proves capability
reporting, not real MP4 decoding or installed production dependencies.
Malformed capability responses disable both editor entry points and issue no
upload request. No subagents were used for this round.

No live OAuth, storage, or publishing was enabled; no deployment, migrations,
dependency installation, shared configuration/model changes, or process restarts
were performed. PostgreSQL target-safety helpers and `test_media_cleanup.py`
remain parent-owned and were neither edited nor run in this round. Existing
untracked frontend preview/cache/dependency artifacts were preserved.

This is a local, unpushed review fix. The parent owns fixture alignment, combined
integration checks, the single push, and subsequent review replies/resolution.
The prior cleanup/retention operational gates remain unchanged.
