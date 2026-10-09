# Independent error-boundary final recheck

**No remaining confirmed diagnostic acceptance defect in the executed matrix.** Both originally confirmed leak mechanisms are repaired. Initial red evidence and report remain intact as `REPORT.md`, `probe-red.py`, `probe-red.log`, `results-red.json`.

Exact pinned HEAD: `97fe77462b4e63ffad7dc393b8bf97d3e51571f7`, source tree `f22a430a4402d79867da63ad97db8c8d474d3a71`, branch `codex/batch8-provider-helper`. The author implementation is still uncommitted at recheck; executed helper blob `96969c07d98f57ec15c2a33e4474e5bcf2b191fa`, SHA256 `9a74e003f90b333c38503ca2fde4683cfd99ddcf70a1b8d5fd4ae1291612b5b1`. Full final helper/test/consumer hashes are recorded in both `results-final-top.json` and `results-final-package.json`.

## Observed results and finding resolutions

- **Valid, repaired — invalid URL port diagnostics:** configured invalid port/userinfo/control-character URL now produces static shared `SupabaseAdminError(500, None)` before transport. Direct raw invalid-port requests likewise produce static 500. No marker in str/repr/args/body/formatted traceback.
- **Valid, repaired — non-ASCII credential/header diagnostics:** configured non-ASCII key produces static shared 500; per-call non-ASCII headers produce static 400. Ordinary formatted tracebacks suppress the encoding exception; Python’s internal exception context remains. Oversized 100,000-character URL/key controls also return bounded static errors.
- **Shared consumers independently executed:** actual active provider list/profile/user/delete/role operations use the shared safe config seam. Signed-auth invalid config/key returns no roles. The actual top-level Users `_provider` wrapper maps these internal 500 failures to its static 502 response. Existing 404/429/503 mappings remain verified, with valid signed admin/auth, valid profile reads/count/roles and genuine empty/missing controls.

Three direct unsupported misuse cases are explicitly retained as observations: `params=object()` raises static AttributeError; nonserializable `json=Unprintable()` raises static TypeError; a raw URL containing a lone surrogate raises UnicodeEncodeError retaining only that lone surrogate, with no sensitive URL or marker. These inputs are outside the supported request contract. They are not sensitive diagnostic leaks and do not justify a catch-all exception handler. Their surfaces were still checked for marker absence and bounded size.

## Executed evidence

| Run | Command outcome | Actual result | Tool output identity |
| --- | --- | --- | --- |
| Initial matrix | exit 1 | 249 cases, 233 pass / 16 fail | `106e08` |
| Initial selected suite | exit 0 | 416 passed, two existing warnings | `f51a24` |
| Recheck extended top-level matrix | exit 1 | 278 cases, 277 pass; only unsupported-surrogate status expectation failed, marker absent | `05e0be` |
| Recheck package harness attempt | exit 1 | harness incorrectly imported router as a package; ModuleNotFoundError for top-level database import | `647b1e` |
| Final top-level matrix | exit 0 | **286/286 pass**, zero socket attempts | `5ce24f` |
| Final supported package matrix | exit 0 | **278/278 pass**, zero socket attempts | `b74bd1` |
| Full relevant final suite | exit 0 | **449 passed**, two existing SQLAlchemy deprecation warnings | `2e4bf1` |

Final matrices total **564 executed cases**. All mock HTTP calls use real `httpx.Client` plus `httpx.MockTransport`; both `socket.socket.connect` and `connect_ex` are blocked before application imports. The package run executes supported `backend.supabase_admin`, `backend.supabase_auth`, and `backend.admin_users_provider` imports; route-wrapper checks run through the router's actual top-level import mode. Package harness correction does not assert a product router-import defect.

`COMMANDS.json` retains command arguments/environment/output paths, observed exit codes and output identities. Raw final logs are `probe-final-top.log`, `probe-final-package.log`, `suite-green.log`; final structured results include exact requests and diagnostic surfaces. Earlier unsuccessful logs are retained without replacement.

The final suite includes both Batch 7 helper/import files, both Batch 8 helper/import files, active Users boundaries/review/adversarial/audit-policy files. Python 3.13.9/macOS 27.0.1 arm64 runtime was reused read only at `/Users/roger/Documents/projects/audit_app/venv/bin/python`. Environments were clean, dotenv and bytecode disabled, pytest cacheprovider disabled, and disposable pytest paths owned by this reviewer.

## Cleanup and limits

No product/test edits, staging, commits or installations were performed by this reviewer. No servers, worker groups, containers, ports, provider calls, production writes or migrations were created. All invoked Python processes completed with recorded exit status. Owned disposable pytest trees were removed; the actual deletion/absence and retained evidence identities are in `CLEANUP.json` and `MANIFEST.json`. The shared runtime and primary checkout were read only. Author worktree remains dirty with its scoped implementation and evidence.

This independently accepts the exercised diagnostic boundary and consumer compatibility at the exact helper hash above. It is not hosted-gate, deployment or live-provider acceptance. Parent should bind this evidence to the final committed source and continue its remaining independent review/PR process.

## Documentation correction after Standards review

**Valid — original retention claim overstated the executed evidence.** The original report is preserved as `REPORT_FINAL_BEFORE_CONTEXT_CORRECTION.md`. Independent execution of the Standards `context_probe.py` also returned exit 0: configured key (500) and per-call header (400) ordinary formatted tracebacks omit the marker, while Python internal `__context__.object` retains the inert marker and `__suppress_context__` is true. `context-correction-recheck.log` retains this observation. Introspection of internal exception context is outside the accepted ordinary diagnostic surfaces (str/repr/args/body/ordinary formatted traceback); no trusted diagnostic channel is added or claimed. This corrects documentation and does not claim a newly demonstrated ordinary-diagnostic product defect. No product/test changes or broad catches were made.
