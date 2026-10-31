# PR861 review disposition

The body-only finding in [review5721966631](https://github.com/Rodgers31/audit_app/pull/861#pullrequestreview-5721966631)
is valid despite that review's contradictory “no active issues” summary.
The mandatory gate covered Social/status reachability but omitted the new
Account, theme and public-site utilities. Existing independent exploration
covered those controls; the required future regression did not.

Root independently ran the original eight assertions twice: baseline8/8 and
8/8 with the actual Account control transparent and unclickable. Separate
browser diagnostics proved the corruption and the existing reachability
helper's refusal. The old mandatory assertions falsely passed; this is a test
coverage defect, not an additional claimed production Account defect.

Four new required flows cover1728/768/375/320px. They hit-test all three
utilities with the private mobile Menu closed and open, toggle theme and check
the DOM/localStorage after reload and Account navigation, leave for the real
public shell and return, navigate to My Account, and sign out through the actual
desktop menu or mobile drawer. The inert logout POST must return204; a subsequent
private entry must refuse. Public desktop navigation is intentionally hidden at
smaller widths, so public ownership checks its one DOM navigation plus a painted,
pointer-reachable brand control. Desktop sign-out uses its actual menuitem role.

The fresh production-build mandatory gate passes **12/12**, zero retries.
No-emit TypeScript and lint on the changed gate pass. The first new test draft
used incorrect desktop/menu visibility assumptions and failed; those setup/test
selection errors are retained externally and receive no product-defect or GREEN
credit. The application/UI/configuration bytes remain identical to reviewed
`d6bb163`; prior2869 frontend unit passes and original shell reviews carry through
those unchanged inputs rather than being relabeled as newly executed tests.

Independent Spec runs the exact four new flows normally and under three browser
corruptions. Baseline4 pass; all12 hidden-Account/covered-theme/covered-public-exit
cases fail at the intended paint/pointer assertion. That counterfactual process
correctly exits1 and is not described as an ordinary passing16-case suite.
Standards independently corroborates the four baseline flows. Neither review
replaces the fresh root production-build12-case gate.

No app, auth, data, backend, financial-generation, worker, schema or activation
code changes are introduced in this review round. Publishing, uploads, workers
and financial generation remain off; no paid review or hosted test was requested.
Production verification and release activation are separate deployment steps.
