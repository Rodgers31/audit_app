"""Registered media availability remains independent of publishing/automation."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from social.api import SystemDTO
from social.service import SocialService
from test_domain_support import db


@pytest.mark.parametrize("allowed", [(), ("image/png",)])
def test_registered_status_reports_actual_media_runtime_without_enabling_automation(db, monkeypatch, allowed):
    monkeypatch.setattr("social.media.runtime.media_runtime", lambda: SimpleNamespace(available_mimes=lambda: allowed))
    status = SocialService(db).status()
    parsed = SystemDTO.model_validate(status)
    assert parsed.media_upload_available is bool(allowed)
    assert parsed.publishing_enabled is False
    assert parsed.adapters_available == ()
    assert not any(getattr(parsed, field) for field in ("generation_enabled", "auto_approve_enabled", "auto_schedule_enabled", "auto_publish_enabled"))
    with pytest.raises(ValidationError):
        SystemDTO.model_validate({**status, "media_upload_available": "true"})
