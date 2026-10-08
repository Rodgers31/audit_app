# Missing video inspector runtime repair — 2026-10-03

## Reproduction and cause

Owned branch `codex/remaining-media-inspector-availability`, frozen root base `4326b46`. Hosted first CI log `A/REMAINING_HOSTED_BACKEND_FIRST.log` shows media API and cleanup failures after `LocalInspector.available_mimes()` constructs `Path(None)`. On the unchanged base, a full media suite with an empty executable PATH (absolute shared Python) reproduces **19 failed, 318 passed, 15 skipped**, 6.60 seconds, without maxfail.

`shutil.which('ffprobe')` returns None when the binary is missing; the media fixture passes that through the real, validated MediaConfig/LocalInspector/MediaRuntime/service. MediaConfig validation previously accepted None despite its string annotation. This is a runtime handling defect for an accepted configuration. Environment construction's absent default is the empty string; it does not itself search PATH or produce None, and that deliberate no-auto-discovery policy is preserved.

A Path-only guard would leave another defect: image inspection passed the same None as an unused child-process argument. An explicitly malformed video path containing NUL similarly must not enter the image decoder's argument list.

## Scoped fix

- Configuration explicitly accepts a string or unset None; bool, numbers, lists and arbitrary objects are rejected during validation.
- LocalInspector normalizes unset to an empty string once. Missing, relative, non-file, non-executable, broken and malformed video paths make only video unavailable. Path/probe errors are contained in the existing bounded capability check.
- Image inspection supplies the child a valid empty video-tool placeholder. Actual Pillow decoding, complete byte-size/digest/dimension checks, process isolation and resource limits remain unchanged.
- Video still requires an explicitly configured absolute executable file, a successful ffprobe version response within two seconds, supported MP4 bytes, H.264/optional AAC, complete frame/sample evidence and the original process/resource limits. No installed binary is fabricated; no MP4 restriction is loosened.
- Deliberate feature disablement and missing image decoder remain no-capability cases; storage enablement/provisioning/configuration is unchanged.

## Regression controls

Fourteen new cases include eight unavailable path forms (None, empty, relative, missing, directory, non-executable, broken executable, NUL). Each drives actual HTTP capabilities, requires JPEG/PNG only and successful image availability, rejects video upload with existing 503 MEDIA_INSPECTOR_UNAVAILABLE before fake storage operations, and decodes actual PNG bytes through the isolated child with exact dimensions and SHA256. Direct MP4 inspection is refused. Four malformed configuration types are rejected; environment-default disablement and missing Pillow plus missing ffprobe advertise no formats.

## Verification

Full `tests/social/test_media_*.py`, normal CI `not slow` marker, no maxfail:

| Runtime | Passed | Skipped | Time |
|---|---:|---:|---:|
| ffprobe/ffmpeg absent from empty executable PATH | 351 | 15 | 8.53s |
| Actual installed /opt/homebrew/bin ffprobe and ffmpeg | 360 | 6 | 11.13s |

Both runs have three existing warnings. The nine additional absent-tool skips are genuine real MP4 decoder/acceptance/corruption controls; all nine execute in the installed-tool run. The six PostgreSQL migration/cleanup controls are skipped in both runs, not claimed executed. Exact skip reasons are retained in logs. No shared dependencies were installed or changed, no provider/storage/production calls occurred, and no root or primary worktree was modified. Empty PATH scratch directories were removed after verification.

The Mac local shared Python differs from hosted Linux/Python3.12; the exact absence condition and complete image-service behavior are reproduced locally, while root's controlled hosted rerun remains the Linux gate.
