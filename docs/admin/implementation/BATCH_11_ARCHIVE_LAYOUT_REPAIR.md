# Historical producer packaging (#629)

The repository's live Python source scan reached the saved, syntax-invalid
`batch11-issue-607-evidence/archive-generators/record_v2.py`. Its original line32
prevented the advertised-endpoint registry and publication-boundary tests from
collecting. [Issue629](https://github.com/Rodgers31/audit_app/issues/629) records
the local and hosted collection failures. This was a collection failure, not a
behavioral regression test or evidence of a deployed route failure.

Only the physical filename changes: `record_v2.py` is now `record_v2.py.txt`.
Its SHA256 remains
`d7e6fb4d511827690d103d6b78946a5e6eecd44c15d0e907519fd90b0c234dfd`;
the saved producer still has the original syntax failure. It is historical byte
input rather than executable source. No source-scanner exclusions, route/API
assertions, financial guards or historical producer bytes were changed.

`batch11-issue-607-evidence/historical-byte-layout.json` declares the one exact
original-to-artifact path correspondence. The additive
`tools/verify_archive_layout.py` validates that correspondence, both unchanged
manifest identities and all65 original archive input hashes. Portable mode
does not invoke Git, so a shallow CI checkout can verify the physical layout.
It refuses restored executable paths, altered or missing bytes, extra inputs,
ambiguous JSON, symlinks and nonordinary objects such as FIFOs. Invoke it with:

```sh
python3 "$CHECKOUT/docs/admin/implementation/batch11-issue-607-evidence/tools/verify_archive_layout.py" \
  --checkout "$CHECKOUT"
```

Add `--require-original-git-bytes` to require a separate literal byte comparison
against the original Git snapshot `26a328ad5b69f0df2efbdefad7de1c0209744ffd`.
That mode uses the absolute system Git binary with inert environment/configuration,
and refuses unavailable history rather than claiming a comparison happened.
Portable results explicitly report `original_git_bytes_verified:false` and
`original_git_bytes_status:"not-requested"`; successful strict results report
`true` and `"verified"`. No workflow fetch policy changes are required.

This is archival layout/integrity verification. It neither executes a saved
producer nor makes historical browser failures, current application behavior,
hosted CI or production acceptable.

Both `packet-v1.json` and `packet-v2.json` retain their exact original bytes and
logical producer path. Original packet README, `tools/verify_packet.py`,
`tools/replay.py` and archived producers retain their bytes too. The original
packet verifier requires the original physical catalogue and therefore belongs
to the frozen historical layout, including its original source qualification.
For that original packet-v2 layout use historical commit
`26a328ad5b69f0df2efbdefad7de1c0209744ffd`; for packet-v1 follow the original
README's historical checkout. It intentionally refuses the current augmented
packet, which also contains the separate current issue census and layout
supplements. Do not rewrite the manifests or revive the malformed executable
path to make that historical reader accept a later tree.

The existing supported `tools/replay.py` imports only the original reader's
report/schema functions; it does not invoke `archive-generators/record_v2.py`.
Its own bytes and behavior remain unchanged. References to the original
producer path in archived receipts/scripts are retained historical identities,
not current replay commands.

The default backend regression preserves the original SHA and SyntaxError32
while asserting that the malformed producer is absent from live source
selection. Its pre-fix execution failed specifically because those bytes were
selected as live Python. A separate planted malformed live `.py` remains
selected by the unchanged whole-tree scanner and the real endpoint parser
raises SyntaxError. Layout negatives protect the original archive catalogue,
and a real shallow-clone fixture accepts portable validation while refusing
the required historical Git comparison.
Current full-suite and hosted acceptance must be checked separately before
closing629; the remaining607 browser issues retain their own dispositions.
