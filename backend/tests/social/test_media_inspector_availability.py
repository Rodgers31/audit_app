"""A missing video tool cannot disable actual image inspection or allow MP4."""
from dataclasses import replace
import hashlib

import pytest

from social.media.config import MediaConfig, config_from_environment
from social.media.inspection import InspectionFailure, LocalInspector
from social.media.runtime import MediaRuntime
from test_media_api import BASE, client, header
from test_media_support import intent, media, media_db, png


@pytest.mark.parametrize('unavailable', ['none', 'empty', 'relative', 'missing', 'directory', 'nonexecutable', 'broken', 'nul'])
def test_unavailable_video_inspector_preserves_images_and_refuses_video(
    media, tmp_path, unavailable
):
    path = tmp_path / 'unavailable-ffprobe'
    if unavailable == 'directory':
        path.mkdir()
    elif unavailable in {'nonexecutable', 'broken'}:
        path.write_text('#!/bin/sh\nexit 2\n')
        path.chmod(0o700 if unavailable == 'broken' else 0o600)
    configured_path = {
        'none': None, 'empty': '', 'relative': 'ffprobe', 'nul': '\x00'
    }.get(unavailable, str(path))
    svc, storage = media
    config = replace(svc.config, ffprobe_path=configured_path)
    inspector = LocalInspector(config)
    svc.runtime = MediaRuntime(config, storage, inspector)

    api = client(media)
    response = api.get(BASE + '/capabilities')
    assert response.status_code == 200, response.text
    assert response.json()['allowed_mime_types'] == ['image/jpeg', 'image/png']
    assert response.json()['upload_available'] is True
    assert storage.operations == []
    response = api.post(BASE + '/uploads', json=intent(
        filename='unsupported.mp4', declared_mime_type='video/mp4'
    ), headers=header())
    assert response.status_code == 503, response.text
    assert response.json()['detail']['code'] == 'MEDIA_INSPECTOR_UNAVAILABLE'
    assert storage.operations == []

    # Actual bytes pass through the isolated image decoder, not a fake tool.
    data = png()
    image_path = tmp_path / 'actual.png'
    image_path.write_bytes(data)
    inspected = inspector.inspect(image_path, 'image/png', len(data))
    assert (inspected.width, inspected.height, inspected.mime_type) == (64, 32, 'image/png')
    assert inspected.sha256 == hashlib.sha256(data).hexdigest()
    with pytest.raises(InspectionFailure, match='capability is unavailable'):
        inspector.inspect(image_path, 'video/mp4', len(data))


@pytest.mark.parametrize('bad_path', [False, 0, [], object()])
def test_video_inspector_path_rejects_malformed_config_types(bad_path):
    with pytest.raises(ValueError, match='executable path'):
        MediaConfig(ffprobe_path=bad_path).validate()


def test_missing_environment_path_does_not_enable_video():
    config = config_from_environment({})
    assert config.enabled is False and config.ffprobe_path == ''
    assert 'video/mp4' not in LocalInspector(config).available_mimes()
    assert MediaRuntime(config, object(), LocalInspector(config)).available_mimes() == ()


def test_missing_image_decoder_and_video_tool_advertise_no_formats(monkeypatch):
    monkeypatch.setattr('social.media.inspection.importlib.util.find_spec', lambda name: None)
    assert LocalInspector(MediaConfig(ffprobe_path=None)).available_mimes() == ()
