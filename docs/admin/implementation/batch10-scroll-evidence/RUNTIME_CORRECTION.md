# Correction to the Node 22 setup annotation

The preserved `data/node22-runtime.json.gz` contains an unsupported `initial_arm64_copy_unused_for_tests` label. The author's first handoff repeated it. Spec review found that the recorded initial and final executable hashes were identical, and the author reproduced the inconsistency with fresh executable/runtime checks.

The first source image's metadata reports `arm64`. Both retained host files (`node22.bin`, `node22-amd64.bin`) identify as ELF x86-64. Both corresponding container executables (`/opt/batch10-scroll-node22/node`, `/opt/batch10-scroll-node22-amd/node`) report Node 22.23.3, platform `linux`, architecture `x64`. All four have SHA-256 `fde6a4bf8d0562f7751d1a2d6cb9b417c4cfe107bbcb0aa3e9a24e125e348f48`.

The earlier ARM64-executable label is withdrawn. The evidence does not establish an overwrite or a lost historical executable, and neither is asserted. The 100-attempt browser command explicitly used `/opt/batch10-scroll-node22-amd/node`; its verified x64 runtime identity and 99-pass/1-pagination-failure outcome remain as recorded. Earlier/full browser runs used the image's Node 24.13.0.

The original archived setup record is unchanged, so the frozen archive remains an exact historical record including this corrected annotation. Fresh exact command arrays, exit statuses, outputs, SHA-256 and readback are in the author's raw root at `node22-runtime-correction.json`. Archive integrity does not independently authenticate runtime claims.
