# Independent Standards review — optional pip-cache bypass

**Configuration-scoped pass: 46/46 executable controls passed, zero failures/errors/skips. No actionable finding.**

Input is branch `codex/pending-bills-runner-cache`, base/HEAD `97546ade5bc89408962908ae90e1fef5a0f447cc`, plus the proposed workflow change. Frozen candidate YAML SHA256: `49a1bf7a44641a88746fc7d3941446a8d07c3efd1de2579168981ef24af3ceba`; accepted YAML: `34ae7b2978a8e2a28d4a9cae616146ded17fc02345b55bd4e928496b65e0377e`. `input-manifest.json` pins both and the author's unexecuted test inventory. The candidate still matches the author checkout after execution.

The independent parser checks the actual full workflow, preserving the `on` trigger key and rejecting duplicate YAML keys. Both parsed structure and literal byte comparison confirm **exactly five `cache: 'pip'` input-line deletions** in `source_plan`, `migrate`, `bootstrap`, `seed`, `validate`. Each retains its exact setup-python action SHA, Python `3.12`, and unchanged direct requirements-install command after setup. The full remainder is identical: source PDF cache steps/keys, TLS qualification, permissions, queue/ordering, timeouts, flags, authority/source commands and dependency commands.

Negative controls execute mutations for every missing job, omitted requirements install and missing Python setup. Additional controls reject malformed/absent schemas, falsey cache inputs, wrong action/version/order, duplicate setup/key definitions, extra jobs, and changes to flags, TLS commands, timeouts, permissions, concurrency or PDF caches. The accepted workflow is explicitly rejected for its remaining optional cache input. These are executable YAML contract checks; **no workflow command or GitHub action is run**.

Receipts: `workflow.txt` / `workflow.xml`; exact test logic is `test_workflow_contract.py`. Execution used the cached Python image `sha256:571e327e2fbe507713d267f6f15050d585a5bbb53b8ec2e3afc73db2996d6d2d`, source inputs read-only, `--network none --cpus 1 --memory 2g --pids-limit 256`. A repeatable host-stdlib orchestrator records exact Docker argv, child exit code and output hashes:

```sh
python3 /Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/release-rollout-20261030/seed-cache-standards-review/replay.py --label independent-replay
```

This removes the explicit optional setup-python pip-cache dependency; it does not increase capacity or prove a GitHub/Azure service fix, successful future dependency installation, source ingestion, database access or production runtime behavior. Actual production flag state was not queried by this review. No product/repository edits, hosted runs, provider requests, cache deletion, services, builds, downloads or installs occurred. The transient test container completed with `--rm`; no owned fixture remains.
