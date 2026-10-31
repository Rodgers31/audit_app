# PR859 worker audit-series fix: independent Spec review

**Scoped pass on frozen candidate 1; no remaining worker-SQL findings.** This does not accept the separately reviewed operator artifact or authorize production/publishing/uploads/workers/financial activation.

## Input and original defect

Frozen candidate: 6,095 files, mapping SHA256 `d6a204b8f7982d91756c7624afcfee99daf317f1c438e79882d55fd29901d1dd`. Full hashes and exact file set verified before/after. Relative to immutable accepted `ee23da4404fb8ced0fd4303ba08eb534a212399b`, the only changed existing backend product files are `native_authority_schema.py` and the two native view-definition pins in `role_contract.py`.

Original executable evidence: **17 desired failures / four passing controls**, zero behavioral-run errors/skips. Both actual PG views returned an unselected same-job audit receipt; the actual restricted Core verifier accepted a genuine previously captured witness after selection changed. The entire series map was absent from its digest dependencies. This confirms the shared invariant finding. The privileged reader already enforced selection; no actual production/publication bypass was attempted or claimed. The stored-witness test models legacy authority or an owner-controlled map change, not a claim that today's privileged producer can freshly mint an unselected receipt.

The sole explicitly assigned permanent test file is unchanged between the corrected baseline RED and final frozen execution. Its first standalone attempt omitted the pg fixture import, yielding 21 setup errors; that attempt is preserved and never credited as behavioral RED.

## Final execution

**24 distinct accepted cases passed in normal Python and the same 24 passed in one clean `-O` run.** The normal evidence comprises 23 successful cases in the first run plus the corrected financial fixture's focused pass. All original failures/logs remain retained.

| Scope | Tests/scenarios |
|---|---|
| Permanent actual restricted-PG regression | 21 cases |
| Independent raw receipt-scope JSON/Unicode guard attacks in both views | 1 case / eight scenarios |
| Non-audit SQL projection preservation | 1 case / all 12 non-audit branch/lock combinations |
| Genuine qualified KRA financial witness dependency preservation | 1 case |

The current view is queried by the real restricted worker login; the snapshot view is queried only by owner. Worker snapshot SELECT remains denied with SQLSTATE42501. `verify_worker_authority` receives a real restricted Core Connection. No ORM authority check substitutes for these SQL assertions.

Selected audit heads still pass. Unselected receipts and missing/null/non-object series, boolean/float/string/nonpositive/foreign heads, and absent/uppercase/foreign scopes have no current/snapshot authority row. Typed raw receipt scopes include booleans, a 32-digit JSON number, null/array/object, uppercase/overlong ASCII and fullwidth Unicode. Mutations are forced and exact JSON readback is checked.

Changing an otherwise unrelated entry in the audit series map changes both-view fingerprints and retires the previously captured witness. The three other native report domains retain their exact previous fingerprint behavior; all 12 generated non-audit SQL projections are unchanged after whitespace normalization. The real qualified financial KRA control also retains its fingerprint and restricted verification after a series-map change.

One initial financial positive correctly refused because its owned synthetic writer's prospective qualification flag was OFF. The fixture was corrected to explicitly qualify that fake writer through the existing gate, then restore financial OFF **before** all source reads/witness verification. No gate was bypassed and no row was manually made publishable. Only that test function changed (AST comparison retained); the other 23 successful normal cases were unchanged. This was a fixture precondition failure, not a product defect or permission to enable production financial generation.

## Provenance and cleanup

All project execution used cached offline Docker (runtime 1 CPU/2 GiB, separate owned PG17 512MiB, unchanged a756b20a0001). Source mounted read-only; no product edits by reviewer. Only the assigned permanent test file was authored, then frozen. No provider, network, production, queue, upload, scheduler or worker action. The owned `pr859-spec-pg` container was removed successfully and private credentials deleted; shared fixtures were untouched.

Commands, XML, immutable source checks, preserved setup/precondition failures and per-case ledger are adjacent. Operator artifact safety and deployment remain separate review/evidence scopes.
