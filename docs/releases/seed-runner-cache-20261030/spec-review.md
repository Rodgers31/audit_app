Scoped configuration change accepted; no finding. This does not certify a successful hosted run or recovery of the cache service.

Executed in owned capped OFFLINE Docker:

- Baseline workflow: **5 executed desired failures**, one per setup-python job.
- Current workflow: **12 passed, zero skips/errors/failures** (author5 + independent7). Exactly five optional pip-cache lines are removed. The entire parsed workflow is otherwise equal, including activation defaults, TLS, plans, permissions, timeouts, Python3.12/action SHA and cold requirements-install steps.
- Pinned provider entry: **11 controls passed**. The actual official setup-python.ts function bodies were transpiled and executed in a Docker VM, with Actions input, installer and cache APIs stubbed. Each of five new job inputs skips both cache-feature checking and restoration; each old pip input reaches the deliberately failing restore sentinel; an unavailable cache feature skips restoration. No installer process was invoked.

Official pinned [entry source](https://github.com/actions/setup-python/blob/ece7cb06caefa5fff74198d8649806c4678c61a1/src/setup-python.ts#L148-L151) and [optional cache input](https://github.com/actions/setup-python/blob/ece7cb06caefa5fff74198d8649806c4678c61a1/action.yml#L10-L12) are saved with download hashes in official-source.json. Only the top-level invocation was instrumented to await completion; provider function bodies were unchanged. Python selection was simulated, and cold dependency installation was verified as present/unchanged in YAML, not performed.

Commands, logs, XML, provider call traces and before/after input hashes are adjacent; all reviewed inputs stayed stable. All runtime containers used network none, CPU1, memory2g and pids256, were removed on exit, and made no project/production/provider writes. The only network reads were the explicitly authorized official pinned source files. No hosted action was triggered. The original hosted timeout diagnosis is root's separate evidence, not independently re-executed here.
