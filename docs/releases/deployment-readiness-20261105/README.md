# Deployment readiness preparation — 5 November 2026

**Release HELD; operational acceptance HELD; media/publishing launch HELD.** This
packet prepares Stage 6 and Stage 7. It neither deploys nor admits a source.
Publishing, media uploads, publishing workers, financial generation, drafts,
shadow, automatic approval/scheduling/publishing and source-generation hooks stay
OFF/held. No production/data/view/pin/schedule/provider mutation is authorized.

The starting engineering commit is `8ef389d7ffc5bfb86bed22ae5a9b63858f13424a`, tree
`75637cdf82b20fdc8190305638d45ca019c838d0`. The packet describes those inspected
source bytes; immutable paired release/runtime/native/PG lane deliveries remain
pending. Do not continuously rebuild moving sibling worktrees. The coordinator
owns integration into existing draft PRs #914/#915, later publication and review
replies. Local tests qualify only this packet's tooling.

Use [GATES.md](GATES.md) as the single actionable gate matrix, then
[RELEASE.md](RELEASE.md), [ROLLBACK.md](ROLLBACK.md),
[OBSERVATION.md](OBSERVATION.md) and [LAUNCH.md](LAUNCH.md). The machine equivalent
is [gate-matrix.json](gate-matrix.json). [EVIDENCE.md](EVIDENCE.md) separates
original observations from summaries. Historical scope remains attached to every
fact; a source ceiling or hash is not an operating reserve or approval.

From the assigned checkout, the following commands are offline. Supply its real
absolute path as `READINESS_ROOT`; supply a fresh already-existing external
private directory as `READINESS_EVIDENCE`. Neither variable is a credential.

```sh
python3 -B "$READINESS_ROOT/scripts/verification/deployment_readiness_20261105/packet.py" \
  --root "$READINESS_ROOT" integrity \
  --manifest "$READINESS_ROOT/docs/releases/deployment-readiness-20261105/source-manifest.json"
python3 -B "$READINESS_ROOT/scripts/verification/deployment_readiness_20261105/packet.py" \
  --root "$READINESS_ROOT" --output "$READINESS_EVIDENCE/readiness-new.json" readiness \
  --manifest "$READINESS_ROOT/docs/releases/deployment-readiness-20261105/source-manifest.json"
python3 -B "$READINESS_ROOT/scripts/verification/deployment_readiness_20261105/packet.py" \
  --root "$READINESS_ROOT" capacity \
  --input "$READINESS_ROOT/scripts/verification/deployment_readiness_20261105/capacity.pending.json"
```

`integrity` exits 0 only for nonempty matching source/packet bytes and a structurally
held matrix. `readiness`, `capacity` and metadata inventory exit **3**, keeping
acceptance pending; malformed/missing/tampered inputs exit **2**. A shell must
handle those exact statuses, not append `|| true`. Output records are exclusive,
external, mode 0600 and read back. Hash integrity does not authenticate an issuer,
reviewer, production observer or owner decision. The pending capacity example's
route references are explicit synthetic placeholders, not observed destinations;
replace them only with existing approved hashed route/login identities.

Inventory JSON is limited to 4 MiB, 32 container levels, 20,000 value nodes and
20 decimal integer digits; floating values must be finite. These are explicit
tool input bounds. A valid but deeper general JSON document is outside this
inventory contract. Directory-name allocation and traversal are bounded before
a census can produce a result, with descriptor-relative binding checks.

The standard-library tests need no install. Run both normal and optimized modes
under `/tmp/auditgava-launch-heavy-20261103.lock`, with empty allowlisted environment,
network denied, source/toolchain read-only, private scratch-only writes and bounded
resources. Do not use the serving interpreter or ambient DB/provider configuration.
The external execution receipts include the actual sandbox, commands, per-case
inventory/raw output and cleanup. They are separate from native/PG/hosted gates.

```sh
python3 -B -m unittest discover -s scripts/verification/deployment_readiness_20261105 -p 'test_*.py' -v
python3 -B -O -m unittest discover -s scripts/verification/deployment_readiness_20261105 -p 'test_*.py' -v
```

No production build, native/source acceptance, actual-host reaper qualification,
fresh saved-grant proof or independent media restore is claimed by these commands.
