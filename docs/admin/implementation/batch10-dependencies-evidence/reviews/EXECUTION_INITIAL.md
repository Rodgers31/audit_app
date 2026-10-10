# Initial independent execution review

Status: validation of pending source only; final signoff awaits frozen corpus.

Scope: `docs/admin/implementation/batch10-dependencies-evidence`; retained-history integrity only. Issue #494 remains OPEN.

Identity:

- HEAD: `041ad89a0a170b4029beb5d9597b55bf934eff7e`
- HEAD tree: `af210e3cf4f30dda6982ad2ac1fa5d999ae28af3`
- Base: `f6c31e271297eece52f34102dc40a1e2ed7069a8`
- Base tree: `69ddfad6deb814dd08fdaee2db2d512d73e14c78`
- Pending diff SHA256: `4eedb0206a2c065dabe8e5d21558777cdd84c5dcd41629541a53c08b793142e8`
- Scope base-to-current diff SHA256: `aa3e50f272eb69fb64008472b6b7245ee07b32c9ed24399bae273979ea7796f2`

Results: published verifier exit 0 (68 records, 482 files); recorder tests exit 0 (8); bundle tests exit 0 (14); direct CLI controls reject 30/30; no inappropriate success observed. Before/after tested identities match. Python 3.9.6, explicit -O, PYTHONOPTIMIZE=1, bytecode writes disabled, TMPDIR owned under this review directory.

Working verifier and bundle-test source contains pending edits, and differs from the archived historical generator copies. This initial report is not committed-source signoff.

Exact calls, input/output hashes, stdout/stderr, and controls are retained in `logs/initial` and `logs/initial-direct`. `INITIAL_REPORT.json` contains identities and all executed/unexecuted boundary labels.

Unexecuted: product remediation/acceptance, historical application reruns, packer regeneration, full optional-field schema coverage, network/containers/GitHub writes/resource exhaustion.
