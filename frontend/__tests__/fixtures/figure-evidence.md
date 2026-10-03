# Figure evidence fixtures

`figure-qualifications.json` and `figure-profile.json` are synthetic SQLite responses captured from the real public verifier and comprehensive county handlers at backend commit `a5d14ae44d4df447308dcb04b3520a82f63b8da0`.

The verifier fixture covers all seven tables. Stored zero observations are independently matched to retained synthetic API bytes; absent measures remain unavailable. The county fixture adds actual county-scoped zero GCP and poverty rows with their own retained observations. These are compatibility fixtures, not downloaded public data or production verification claims.

The capture runner and receipts are retained in the session evidence bank as `REMAINING_UI_DTO_CAPTURE.py`, `REMAINING_UI_DTO_TEST.py`, and `REMAINING_UI_DTO_CAPTURE.log`. Status downgrade tests deliberately vary the compatible DTO to exercise the presentation and refresh boundary.
