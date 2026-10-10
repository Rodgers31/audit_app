# Lane-local lessons for the coordinator

- Reproduce CSS with the actual content scanner and a real browser. Compiling a migrated stylesheet does not establish compatibility for unchanged class strings. Official migration source changes matter as much as package deltas.
- Keep unit-test environment distinct from build/preview fixtures. Fake Supabase credentials activate auth logic under timers and caused real retry-budget failures; existing CI deliberately omits them for Jest.
- Capture a recorder's starting bytes, and inventory additions as well as changes/deletions. Collapsed untracked directories can hide new consumed files. Preserve failed attempts and old generators rather than rewriting receipts.
- Skip only the optional GPU downloader, then prove CPU inference still executes. Model loading and actual fresh embedding-builder outputs are separate checks from importing a native module.
- Quantify lock drift, including production records, in discarded fresh-resolution candidates. A smaller audit count can still retain every advisory root.
- Attach cache environment before the very first npm metadata lookup. An early lookup here used the default metadata cache; later commands consistently used lane-owned cache.

These are proposed shared-workflow lessons. Shared skills were not edited concurrently.
