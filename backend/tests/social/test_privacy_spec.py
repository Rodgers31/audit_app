"""Independent PostgreSQL uniqueness controls with distinct primary keys."""
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_privacy_postgres import privacy_pg
from test_privacy_support import config, connected, graph, privacy, signed


@pytest.mark.parametrize(
    "table,columns,constraint",
    [
        (
            "social_privacy_receipts",
            "id,app_id,kind,digest_version,subject_digest,event_key,"
            "request_fingerprint,issued_at,provider_expires,received_at,affected,"
            "resolution,state,audit_id,confirmation_hash,confirmation_key_version,"
            "encrypted_confirmation,status_url_base",
            "uq_social_privacy_event",
        ),
        (
            "social_privacy_request_variants",
            "id,app_id,kind,fingerprint,receipt_id,received_at",
            "uq_social_privacy_variant",
        ),
        (
            "social_privacy_ownership",
            "id,app_id,digest_version,subject_digest,reference_key,flow_id,"
            "credential_id,credential_version,account_id,page_id,generation_at,"
            "created_at",
            "social_privacy_ownership_reference_key_key",
        ),
    ],
)
def test_private_postgres_identity_constraints_are_not_primary_key_proofs(
    privacy_pg, config, graph, table, columns, constraint
):
    with Session(privacy_pg) as db:
        connected(db, config, graph)
        privacy(db, config).receive(signed(config), kind="data_deletion")

    # Use a new PK for every attempted row. For receipts also use a distinct
    # confirmation hash, so that only the canonical event constraint conflicts.
    params = {"id": str(uuid4()), "confirmation_hash": uuid4().hex * 2}
    expressions = [
        "CAST(:id AS uuid)" if column == "id"
        else ":confirmation_hash" if column == "confirmation_hash"
        else column
        for column in columns.split(",")
    ]
    statement = text(
        f"INSERT INTO {table} ({columns}) "
        f"SELECT {','.join(expressions)} FROM {table} LIMIT 1"
    )
    with pytest.raises(IntegrityError) as caught:
        with privacy_pg.begin() as conn:
            conn.execute(statement, params)
    assert caught.value.orig.diag.constraint_name == constraint
