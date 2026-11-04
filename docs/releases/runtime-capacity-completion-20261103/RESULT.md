# Runtime capacity follow-through — 3 November 2026

Base is `e94eb980190f6074dcfc0f8ec6f9317fc74cfba0`, tree
`2d62058b07f8a23dbc2f0bdf3c15f46121b90e1e`. This lane changes only the
offline V2 assessor, its regression fixture and these new documents. Application
runtime code, historical producers, held codec packet, build definitions and
workflows are unchanged. The new backend test is part of the backend Docker
context because tests are copied; the context is not byte-identical. No rebuild
or deployment was performed.
The parent retains merge, deployment, admission-pin and later activation authority.

## Current serving-host codec result

The final PR908 command ran once on the existing serving host at
**8:52:54 p.m. CST, 3 November / 02:52:54 UTC, 4 November**. It completed in
2.210037 seconds with shell exit zero. Its exact 18,664 bytes hash to
`afb8d6ed7c7660d7996edb3acb93412a01fa16a89e0bc9c80c7a925573b3d782`;
executed runner SHA256 is
`6fc2e8db5884251806f1db65ce54dde25428d84d8a91014655a584f8be03dff8`.
Fresh PR908 review bodies, all inline comments and issue comments were read with
complete pagination before execution. The earlier old-runner result is preserved
under its original identity; it is not the basis of this pass.

Actual runtime was Linux x86_64/Python 3.12.16, source
`f0f4705e9561e2e42edd93fc747e8bff24468fae`, one existing 512 MiB/0.5 CPU
allocation. Both images were 64×32: PNG 133 bytes and JPEG 661 bytes. H264 was
1,844 bytes, 64×32, 1,000 ms, 10 fps, no audio. All nine wrong-MIME,
wrong-length and malformed-input controls refused. Product/binary/input pins
matched; all owned temporary directories were removed. The packet reports zero
database connections/provider calls, no worker start and upload/delivery,
capacity and launch acceptance all false.

Protected observations at 02:51:35 and 02:53:25 UTC match in every field except
timestamp: schema `a756b20a0001`, global controls version 3 all false, connected
Facebook/Instagram both publishing paused, eight posts/ten revisions and zero
assets/uploads/targets/publications/attempts, zero coarse social/admin worker
processes, live/ready 200 and private-admin 401. Distinct-master observations at
02:52:22 and 02:53:58 UTC match except time: version 7 drafts/shadow false.
Both repository generation hooks were freshly read false; nightly remained enabled
and main/admission pin matched the base. No controls or credentials were changed.

These are **post-nightly baselines**: the ordinary admitted scheduled run
41759203897 had already failed. Its legitimate preceding writes are not attributed
to this codec check. The nightly lane owns its domain/cache diagnosis. No refresh
or rerun was dispatched here.

The raw stdout exceeded the rendered terminal viewport. Its full JSON was recovered
from visible scrollback with exact 179-byte and 5,549-byte overlapping segments,
then parsed without reconstruction of missing fields. The exit marker and both
protected readbacks are retained separately. This is operator-observed UI evidence,
not a signed provider export or an atomic lock on later state.

## Reproduced offline accounting defect

`qualification.py` selects POST mutations and image GETs before pairing events.
V2 previously inherited that selection without accounting for remaining events.
A real inert `Endpoint.respond(GET /foreign-target)` emits a start, returns 400
and raises; adding that emitted event to an otherwise complete packet still
returned a numerical capacity result. An unfinished Graph read and an unsupported
method were also discarded. This is a measurement-tool defect; no production
misclassification or live worker defect was asserted.

The new V2 implementation accounts for every event before the frozen calculation:
only supported methods, exact cohort media/mutation routes, auth reads, or Graph
reads of saved remote IDs using the selected Graph version are admitted. Every
request requires one start and one completion with identical method/path/ID,
finite ordered times within the window and valid supplied byte counters. Unknown,
foreign, duplicate, combined or unfinished observations refuse. The successful
result reports `observed_operations`; it still explicitly says unauthenticated
offline telemetry and `production_accepted=false`.

The public loader, `qualification.py`, `run.py`, `bounded.py` and the old receipts
remain unchanged. V1 producer verdicts do not acquire this correction. New V2
results have a different executed-assessor hash. Reassessment requires complete
original inputs; missing data stays unavailable. No old artifact is overwritten.

Author regressions were observed red at the fixed base in normal/optimized
Python 3.13.9: three expected-refusal failures and one live baseline pass per
mode. The corrected seven-method fixture passes per mode, as do the existing
21 V2 methods and 31 held-packet methods in separate selections. Independent
review and same-package sandbox outcomes are recorded in the private handoff.
The cached serving image's original 81 packages and 1,506 shipped source files
matched the retained serving inventory. With the then-frozen source mounted read-only,
89 selected cases plus 56 nested subcases passed per normal/`-O` pytest-parent mode;
14 additional distinct real-PostgreSQL native text/recovery/CLI cases passed per
mode. These include checkpoint restarts, ambiguous outcomes without blind resend,
completion persistence failure and startup/closure/cancellation failures. App
x86_64 ran emulated on macOS ARM; PostgreSQL17 was ARM. Six exact owned containers
and one owned volume were positively removed. This is local behavior qualification,
not serving or combined capacity acceptance. An initial noexec-tmpfs setup failure
and later busy-lock refusals are preserved; the corrected fixture used executable
owned tmpfs. Fresh supervisor/CLI child interpreters did not inherit `-O`; the
in-process native worker/repository did. The seven-method regression was later
tightened to require the intended guard diagnostic on valid routes, then passed
separately in normal/optimized local Python 3.13.9. A targeted same-package replay
of those corrected test bytes was refused by the busy shared lock; the earlier
89-case receipt retains its original test hashes. Product code did not change.
Counts across overlapping selections or modes are not added.

## Qualification boundary

The current allocation fitted this tiny codec packet. It does **not** yet admit
the proposed concurrent active workload: whole-worker/browser/API/DB/egress peaks,
current host stop window and positive accepted reserves remain incomplete.
[BUDGET.md](BUDGET.md) distinguishes process/client/backend units and observations
from ceilings. [CANARY.md](CANARY.md) fixes the separate future idle packet and
active acceptance requirements. No live worker, production ownership acquisition/release, real
media intake, provider send, restore/export, flag/policy installation or resource
change was performed or authorized by this result. Prior accepted shutdown,
custody, logical-restore and notice/grant proofs retain their actual dated scopes.
