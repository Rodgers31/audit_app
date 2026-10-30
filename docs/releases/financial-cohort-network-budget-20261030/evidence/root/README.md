# Root validation archive

These are original byte-exact logs, commands, JUnit and child-exit records. Checking their hashes verifies archive integrity; it does not rerun acceptance. The original 846 normal/846 optimized cases describe candidate7 and the backend at d0da4996327213049614cd8f09b373bcaa856a23. The supplemental 225 normal/225 optimized cases describe candidate8, including the reviewed per-phase CLI repair. Counts overlap; do not add them as unique tests.

Candidate8 differs from7 only in one product file, backend/seeding/cli.py; its other backend changes are tests. The complete source manifests/identities are included. All current backend files were matched to candidate8 before recording the supplemental receipt. Documentation/evidence files were appended after execution. The three permanent hard-alarm cases were observed failing on the original d0 code; the REDs are deliberately excluded from passing results.

The exact archived commands contain old workstation mount/env-file paths for provenance and are not portable replay recipes. They contain no credential values. Current tests are ordinary repository tests using the existing guarded owned PostgreSQL fixtures. The Standards archive provides its separate pinned historical replay recipe.

Verify bytes from this directory with `sha256sum -c SHA256SUMS` (or `shasum -a 256 -c SHA256SUMS` on macOS). No network, provider, worker or database access is needed for this integrity check.
