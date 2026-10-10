# Portable diagnostic archive

This archive preserves the unresolved #601 investigation, including the original historical failure and the author's later mixed results. See [the handoff](../BATCH_10_SCROLL_HANDOFF.md) for interpretation and runtime differences.

From the repository root, with Node 22 or newer:

```sh
node docs/admin/implementation/batch10-scroll-evidence/verify.mjs
node --test docs/admin/implementation/batch10-scroll-evidence/verify.test.mjs
```

The verifier binds the complete frozen raw-input census and executes the repository's actual original browser-result parser. Its exit status describes archive integrity only. It always reports `issue_601: unresolved`, and preserves the Node 22 replay's pagination failure rather than certifying that record as a pass. Independent review and final published replay records are kept separately, so they cannot rewrite the archived historical attempts. This verifier checks this specific publication; it does not accept arbitrary newly generated receipts.

`manifest.json` lists every regular file under `data/`, its compressed and original SHA-256, 386 product/test/config source hashes, historical execution identity, six full cohorts and six targeted records. Files are gzip archives, including the original trace ZIP and the separate pagination-failure attachments. To inspect an input, decompress its named `.gz` file to an owned temporary directory. Passing trace/video assets from other probes remain at the external raw root identified in the handoff; the committed raw reports retain their attachment pointers. The archive does not authenticate who created a receipt.

`create_package.py` published these 62 completed inputs with exclusive output creation, input stability checks and readback. Publication v1 (59 inputs) remains unchanged at the external raw root's `publication-v1/`; v2 adds the original inventory receipt/log and full parent raw log. The consumed publisher bytes are preserved as `data/publisher.py.gz`; every consumed command-receipt generator and measurement hook version is also archived. The current publisher refuses to overwrite inherited output. Regeneration requires a new owned destination and a separately labeled publication, preserving this package.

The hostile-input tests call `verifyPackage` directly against owned temporary copies. They exercise absent/malformed inventories, omitted/unlisted/changed/duplicate/symlinked data, zero-test reports, infrastructure failures, false green relabeling, source/historical drift, incomplete cohorts and invalid counters. Fourteen independently reproduced false-success mutations fail the old verifier's regression controls and are rejected by the amended verifier. They do not test or repair application scroll restoration.
