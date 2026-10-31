# PR861 / PR862 review-fix verification

**Scoped acceptance: both review findings are addressed; no remaining finding in the executed scope.** No product/test checkout edits were made by Spec. Original pre-fix review evidence remains untouched in the parent directory.

## PR861 mandatory browser gate

Executed the exact corrected mandatory module, SHA256 `8a68fc902aa5dcd5606f23e16bff9fcef405eff17fabe21facdbfbc7cb160b03`, through an external wrapper. The four actual utility tests pass at1728,768,375 and320px. They check Account/theme/public-site reachability, mobile task Menu closed/open, actual theme class and stored preference across reload, public exit and Back, Account heading with retained theme, actual desktop/mobile inert sign-outPOST204 and subsequent private-entry refusal.

Three independent counterfactual environments corrupt one actual utility at a time: Account receives opacity0 and pointer-events:none through a response-only CSS append; a fixed sibling overlay covers the theme button; the same kind of overlay covers the public-site identity. **All12 mutant cases are rejected by the intended mandatory assertion**: four Account paint refusals, four theme pointer-hit refusals and four public-exit pointer-hit refusals. Actual per-case diagnostics prove the hidden style/cover center hit, including desktop1728 and phone320. These refusals come from the unchanged frozen mandatory test, not an extra expected-failure assertion in the wrapper.

Raw Playwright result is deliberately **4 passed /12 failed /0 skipped, exit1**,25.1s. The12 failures are the desired counterfactual refusals. They are not relabeled as an ordinary all-green suite. The Python orchestration process completes normally after collecting that child exit; `exit.json` retains the actual Playwright failure status. `executed-browser-cases.json` enumerates and classifies every result. The earlier original8-case gate demonstrably passed with hidden Account; that sealed16-case comparison remains separate.

The app uses the explicitly authorized cached Next BuildID `bP5LaL8giTBgzvDjz7Yke`; no fresh-build claim is made here. All836 unchanged frontend source files were rehashed against the prior reviewed mapping; the only UI delta is the executed mandatory test. Root separately ran its fresh default12-case build/gate successfully; that observed result is not counted as independent Spec execution. The initial new-test draft was corrected by root for actual responsive public-nav semantics before this independent execution; the unexecuted draft is preserved separately.

## PR862 portable replay helpers

The two exact changed launcher artifacts are pinned as:

- `run-root-tests.py.bytes`: `f261d9a5642984781e9f223f5baf5dca61aba1dcc6dfaefecf4341de9a38b3bc`
- `run-final-selection.py.bytes`: `2d94e8e1fb687d03c0499cb2b1e8b951f3ade0fa08b3c79a09362a67171a3d6a`

Independent stdlib controls pass **6 normal +6 true optimized (`python3 -O`)**. Every Docker call is intercepted by a fake executable; no actual container/database command is run. Controls execute ancestor source inference and fresh default evidence creation; spaced explicit source/evidence overrides and optimized child arguments; each existing receipt extension plus dangling symlink refusal before child execution; invalid/blank overrides without fallback; child exit29 propagated both to caller and saved command receipt; committed selection and unique companion names plus missing-input refusal. The generated command retains the capped local runtime and OFF flags. Source and README bytes match their pre-run pins after execution.

This verifies portable launch/receipt behavior. It does not credit fake child success as real backend test execution or claim the cached runtime/guarded owned PostgreSQL prerequisites are provisioned. The README states those prerequisites and separates portable entry points from immutable historical receipts.

## Reproduction and limits

`command.json` records the exact browser command. `gate.config.ts` filters only the four requested utility cases; `gate-external.spec.ts` imports the frozen mandatory module without assertion edits. `run_gate.py` owns its local service/Next process groups and refuses occupied ports. To rerun, first select a fresh output directory/config; do not overwrite this sealed packet. Portable commands are `python3 test_portable_independent.py` and `python3 -O test_portable_independent.py`; all temporary fake-CLI input/receipt directories are cleaned by unittest.

`FINAL-RECEIPT.json` pins inputs, scripts, raw results and every actual browser diagnostic. Own ports3137/8137 were verified closed at completion; no shared services, user processes or containers were stopped. No production, external provider, paid resource, worker, publishing or upload action was used. This acceptance is bounded to the two review repairs; it is not a deployment or entire-application certification.
