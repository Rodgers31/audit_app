"""Direct domain callers must obey the same version rules as HTTP callers."""
from types import SimpleNamespace
from uuid import UUID

import pytest

from social.service import SocialError
from test_domain_support import call, db, draft_body


@pytest.mark.parametrize("version", [True, False, 0, -1, 1.0, float("nan"), None])
def test_direct_submit_rejects_invalid_versions_without_mutation(db, version):
    body = draft_body()
    _, post = call(db, body, lambda svc: svc.create(body), route="create")
    from social.service import SocialService
    with pytest.raises(SocialError) as rejected:
        SocialService(db)._locked(UUID(post["id"]), version)
    assert rejected.value.code == "INVALID_REQUEST"
    assert rejected.value.status == 422
    assert SocialService(db).detail(UUID(post["id"]))["version"] == 1


def test_direct_validation_and_controls_reject_boolean_versions(db):
    body = draft_body()
    _, post = call(db, body, lambda svc: svc.create(body), route="create")
    from social.service import SocialService
    svc = SocialService(db)
    for command in [
        lambda: svc.validate(UUID(post["id"]), SimpleNamespace(expected_version=True)),
        lambda: svc.controls(SimpleNamespace(expected_version=True, publishing_enabled=False, reason="Fixture")),
    ]:
        with pytest.raises(SocialError) as rejected:
            command()
        assert rejected.value.code == "INVALID_REQUEST"
