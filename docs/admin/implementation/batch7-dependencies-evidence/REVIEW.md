# Independent reviews

Source base: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`; issue #494, parent #545 and frozen Batch 7 specification.

Adversarial reviewer executed the runtime and actual browser verifiers. It found a nested braces copy could still produce the root-resolution-only absence verdict. Author reproduced the false green (`adversarial-nested-red.log`), added recursive installed-package inspection and dependency-map validation, then retained the rejecting replay (`adversarial-nested-green.log`) and persistent real-installation regressions. The installed native decoder positive control still succeeds. Final independent replay and Standards/Spec reports will be recorded before delivery.
