# Lossless command-output envelopes

Selected command outputs are committed as `.log.json` so original carriage returns, indentation and trailing spaces are preserved without introducing source-whitespace failures. `text` contains the exact UTF-8 decoded bytes; encode it as UTF-8 and compare SHA256 with `sha256`. `raw_file` identifies the retained original in the owned raw evidence. All 27 envelopes were verified byte-for-byte against those originals. The earlier review snapshots refer to the original `.log` copies; their content is preserved exactly by these envelopes.

The publisher release-note file is a compact review summary. Full original publisher text remains under the recorded raw-root/hash. Later delivery documentation does not change the reviewed product files.

[Independent format review](standards-format-followup.md) verifies all 27 envelopes reproduce the original 37,762 bytes and declared hashes exactly, with zero findings.
