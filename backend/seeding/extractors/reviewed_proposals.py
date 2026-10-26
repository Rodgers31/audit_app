"""Explicit, source-checked repair receipts; never selected by a nightly default."""
import json
from pathlib import Path

from .reconciliation import _digest, _row, IncompleteExtraction

REVIEW_IDS = ("oag-2542-20261026",)


def without_binding(row):
    # Acquisition time changes on a fresh verified download. The extractor's
    # actual read and validate_candidates still bind it to the exact source.
    # Retain every other payload, page and confidence field in the digest.
    return {**row, "payload": {
        k: v for k, v in row["payload"].items()
        if k != "pdf_artifact_binding_v1"
    }}


def approve(proposal, rows, review_id):
    if type(review_id) is not str or review_id not in REVIEW_IDS:
        raise IncompleteExtraction("unknown source-checked reconciliation review")
    manifest = json.loads((Path(__file__).parent / "reviews" / (review_id + ".json")).read_text())
    from ..pdf_artifact import BINDING_KEY, valid_binding
    for row in rows:
        binding = row.extracted_json.get(BINDING_KEY)
        if (not valid_binding(binding)
                or binding["artifact"]["sha256"] != proposal["source_sha256"]
                or binding["artifact"]["md5"] != proposal["source_md5"]
                or binding["artifact"]["source_document_id"] != proposal["document_id"]
                or binding["artifact"]["source_url"] != proposal["source_url"]):
            raise IncompleteExtraction("source-checked review requires every actual PDF binding")
    snapshot = {k: v for k, v in proposal.items() if k != "candidate_sha256"}
    snapshot["revised_rows"] = [
        {**r, "after": without_binding(r["after"])}
        for r in proposal["revised_rows"]
    ]
    if (_digest(snapshot) != manifest["proposal_content_sha256"]
            or _digest([without_binding(_row(r)) for r in rows])
            != manifest["candidate_content_sha256"]):
        raise IncompleteExtraction("source-checked review differs from current reconciliation")
    return {"proposal": proposal, "source_complete": True,
            "reason": manifest["reason"], "review_id": review_id,
            "review_manifest_sha256": _digest(manifest)}
