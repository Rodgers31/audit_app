"""Review regressions using isolated SQLite and explicit inspection dependencies."""
from dataclasses import replace

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from social.media import inspection
from social.media.contracts import UploadIntent
from social.media.inspection import LocalInspector
from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.runtime import MediaRuntime
from social.models import SocialAuditEvent, SocialMediaAsset
from test_media_api import BASE, client, header
from test_media_support import intent, media, media_db


CONTROLS = [*range(32), 127]


@pytest.mark.parametrize('codepoint', CONTROLS)
def test_filename_contract_rejects_every_c0_and_del(codepoint):
    with pytest.raises(ValidationError):
        UploadIntent.model_validate(intent(filename=f'bad{chr(codepoint)}.png'))


@pytest.mark.parametrize('codepoint', CONTROLS)
def test_filename_api_rejection_precedes_reservations_and_storage(media, codepoint):
    svc, storage = media
    response = client(media).post(BASE + '/uploads', json=intent(filename=f'bad{chr(codepoint)}.png'), headers=header())
    assert response.status_code == 422, response.text
    assert response.json()['detail']['code'] == 'INVALID_REQUEST'
    assert response.headers['cache-control'] == 'private, no-store'
    assert storage.operations == []
    for model in (SocialMediaAsset, SocialMediaUpload, SocialMediaBudget, SocialAuditEvent):
        assert svc.db.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize('filename', ['actual.png', 'team photo.v2.png', 'évidence_日本語.png'])
def test_filename_contract_preserves_supported_names(filename):
    assert UploadIntent.model_validate(intent(filename=filename)).filename == filename


@pytest.mark.parametrize('images,videos,expected', [
    (True, True, ['image/jpeg', 'image/png', 'video/mp4']),
    (True, False, ['image/jpeg', 'image/png']),
    (False, True, ['video/mp4']),
    (False, False, []),
])
def test_api_capabilities_follow_available_inspectors(media, monkeypatch, tmp_path, images, videos, expected):
    svc, storage = media
    if not images:
        monkeypatch.setattr(inspection.importlib.util, 'find_spec', lambda name: None)
    probe = tmp_path / 'ffprobe'
    if videos:
        probe.write_text("#!/bin/sh\nprintf 'ffprobe version review-fixture\\n'\n")
        probe.chmod(0o700)
    config = replace(svc.config, ffprobe_path=str(probe))
    svc.runtime = MediaRuntime(config, storage, LocalInspector(config))
    response = client(media).get(BASE + '/capabilities')
    assert response.status_code == 200
    data = response.json()
    assert data['allowed_mime_types'] == expected
    assert data['upload_available'] is bool(expected)
    assert data['library_available'] is True
    assert (data['unavailable_reason'] is None) is bool(expected)
    assert storage.operations == []


@pytest.mark.parametrize('missing', ['enablement', 'storage', 'inspector'])
def test_runtime_cannot_advertise_uploads_without_each_requirement(media, missing):
    svc, storage = media
    config = replace(svc.config, enabled=False) if missing == 'enablement' else svc.config
    svc.runtime = MediaRuntime(config, None if missing == 'storage' else storage, None if missing == 'inspector' else svc.runtime.inspector)
    data = client(media).get(BASE + '/capabilities').json()
    assert data['upload_available'] is False
    assert data['allowed_mime_types'] == []
    assert data['unavailable_reason']
    assert storage.operations == []
