"""Executable inspector attacks; temporary files and subprocess fakes only."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from types import SimpleNamespace
import zlib

import pytest

from social.media.config import MediaConfig
from social.media import inspection
from social.media.inspection import InspectionFailure, LocalInspector


def png_bytes():
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\0\xff\0\0')) + chunk(b'IEND', b'')


@pytest.fixture
def png(tmp_path):
    path = tmp_path / 'one-pixel.png'
    path.write_bytes(png_bytes())
    return path


@pytest.fixture
def fake_inspector(monkeypatch):
    monkeypatch.setattr(LocalInspector, 'available_mimes', lambda self: ('image/png', 'image/jpeg', 'video/mp4'))
    return LocalInspector(MediaConfig(ffprobe_path='/explicit/test/fake-ffprobe'))


@pytest.fixture
def fake_mp4(tmp_path):
    path = tmp_path / 'header-only.mp4'
    path.write_bytes(struct.pack('!I', 24) + b'ftypisom' + b'\0' * 20)
    return path


def child_output(monkeypatch, data, returncode=0):
    raw = data if isinstance(data, bytes) else json.dumps(data).encode()
    def run(*args, **kwargs):
        kwargs['stdout'].write(raw)
        return SimpleNamespace(returncode=returncode)
    monkeypatch.setattr(inspection.subprocess, 'run', run)


def image_result(**overrides):
    return {'mime_type': 'image/png', 'width': 1, 'height': 1, 'duration_ms': None, 'frame_rate': None, 'codec_metadata': {}, **overrides}


def video_result(stream=None, duration='1.0', format_name='mov,mp4,m4a,3gp,3g2,mj2', streams=None):
    picture = {'codec_type': 'video', 'codec_name': 'h264', 'width': 16, 'height': 16, 'avg_frame_rate': '30/1', 'nb_read_packets': '1', 'nb_read_frames': '1', 'nb_frames': '1', **(stream or {})}
    return {'streams': [picture] if streams is None else streams, 'format': {'duration': duration, 'format_name': format_name}}


@pytest.fixture
def readonly_real_child(monkeypatch):
    """Keep the installed shared Python packages read-only when running -I."""
    original = subprocess.run
    def run(args, **kwargs):
        if len(args) > 1 and args[1] == '-I':
            args = [args[0], '-B', *args[1:]]
        return original(args, **kwargs)
    monkeypatch.setattr(inspection.subprocess, 'run', run)


def test_actual_png_round_trip_has_positive_byte_and_digest_evidence(png, readonly_real_child):
    result = LocalInspector(MediaConfig()).inspect(png, 'image/png', png.stat().st_size)
    assert (result.width, result.height, result.mime_type) == (1, 1, 'image/png')
    assert result.sha256 == hashlib.sha256(png.read_bytes()).hexdigest()
    assert result.duration_ms is None and result.frame_rate is None and result.codec_metadata == {}


def test_actual_animated_png_is_not_a_supported_static_image(tmp_path, readonly_real_child):
    from PIL import Image
    path = tmp_path / 'animated.png'
    Image.new('RGB', (1, 1), 'red').save(path, format='PNG', save_all=True, append_images=[Image.new('RGB', (1, 1), 'blue')], duration=100, loop=0)
    with pytest.raises(InspectionFailure):
        LocalInspector(MediaConfig()).inspect(path, 'image/png', path.stat().st_size)


def test_actual_jpeg_has_positive_decoded_evidence(tmp_path, readonly_real_child):
    from PIL import Image
    path = tmp_path / 'one-pixel.jpg'
    Image.new('RGB', (1, 1), 'red').save(path, format='JPEG')
    result = LocalInspector(MediaConfig()).inspect(path, 'image/jpeg', path.stat().st_size)
    assert (result.width, result.height, result.mime_type) == (1, 1, 'image/jpeg')
    assert result.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('body,mime', [
    (b'', 'image/png'), (b'not an image', 'image/png'), (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (png_bytes()[:33], 'image/png'), (png_bytes()[:-12], 'image/png'),
    (png_bytes()[:-20], 'image/png'), (b'\xff\xd8\xff\xe0' + b'garbage' * 10, 'image/jpeg'),
    (png_bytes(), 'image/jpeg'), (b'GIF89a' + b'\0' * 32, 'image/png'),
])
def test_actual_empty_truncated_and_spoofed_files_are_not_ready(tmp_path, readonly_real_child, body, mime):
    path = tmp_path / 'hostile-bytes'
    path.write_bytes(body)
    with pytest.raises(InspectionFailure):
        LocalInspector(MediaConfig()).inspect(path, mime, len(body))


def test_missing_file_is_a_typed_inspection_failure(tmp_path, fake_inspector):
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(tmp_path / 'missing.png', 'image/png', 12)


@pytest.mark.parametrize('size', [None, True, False, 0, -1, 1.5, float('nan'), float('inf'), '69'])
def test_direct_expected_size_guards_reject_hostile_numbers(png, fake_inspector, size):
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(png, 'image/png', size)


@pytest.mark.parametrize('value', [None, True, False, 0, -1, 1.5, float('nan'), float('inf'), '1', {}, [], 10001])
def test_image_dimensions_cannot_pass_on_bool_or_hostile_numbers(png, fake_inspector, monkeypatch, value):
    child_output(monkeypatch, image_result(width=value))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(png, 'image/png', png.stat().st_size)


@pytest.mark.parametrize('metadata', [
    {'duration_ms': True}, {'duration_ms': 0}, {'duration_ms': -1}, {'duration_ms': float('nan')},
    {'duration_ms': float('inf')}, {'duration_ms': 'unknown'}, {'frame_rate': True},
    {'frame_rate': float('nan')}, {'frame_rate': float('inf')}, {'codec_metadata': None},
    {'codec_metadata': []}, {'codec_metadata': 'success'}, {'codec_metadata': {'value': float('nan')}},
    {'codec_metadata': {'value': float('inf')}},
])
def test_image_child_metadata_cannot_certify_invalid_ready_values(png, fake_inspector, monkeypatch, metadata):
    child_output(monkeypatch, image_result(**metadata))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(png, 'image/png', png.stat().st_size)


@pytest.mark.parametrize('body', [b'', b'not json', b'null', b'[]', b'{}', b'true', b'"successful"', b'x' * (64 * 1024 + 1)])
def test_absent_malformed_or_oversized_child_output_fails(png, fake_inspector, monkeypatch, body):
    child_output(monkeypatch, body)
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(png, 'image/png', png.stat().st_size)


@pytest.mark.parametrize('returncode', [1, 2, -9])
def test_nonzero_child_exit_never_uses_success_shaped_output(png, fake_inspector, monkeypatch, returncode):
    child_output(monkeypatch, image_result(), returncode=returncode)
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(png, 'image/png', png.stat().st_size)


@pytest.mark.parametrize('exception', [subprocess.TimeoutExpired('test-child', 1), PermissionError('test'), OSError('test')])
def test_resource_timeout_or_broken_child_is_typed_failure(png, fake_inspector, monkeypatch, exception):
    def broken(*args, **kwargs):
        raise exception
    monkeypatch.setattr(inspection.subprocess, 'run', broken)
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(png, 'image/png', png.stat().st_size)


@pytest.mark.parametrize('stream', [None, True, 1, 'video', [], {}])
def test_malformed_video_stream_items_are_typed_failures(fake_mp4, fake_inspector, monkeypatch, stream):
    child_output(monkeypatch, video_result(streams=[stream]))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)


def test_valid_tool_video_result_has_positive_metadata(fake_mp4, fake_inspector, monkeypatch):
    child_output(monkeypatch, video_result())
    result = fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)
    assert (result.width, result.height, result.duration_ms, result.frame_rate) == (16, 16, 1000, 30.0)


@pytest.mark.parametrize('streams', [[], {}, True, [video_result()['streams'][0]] * 2, [video_result()['streams'][0]] * 5, [{'codec_type': 'subtitle'}]])
def test_invalid_or_multiple_video_streams_are_not_ready(fake_mp4, fake_inspector, monkeypatch, streams):
    child_output(monkeypatch, video_result(streams=streams))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)


@pytest.mark.parametrize('duration', [True, False, None, 0, -1, float('nan'), float('inf'), '-inf', 'NaN', '0', '121'])
def test_video_duration_requires_finite_positive_non_boolean_evidence(fake_mp4, fake_inspector, monkeypatch, duration):
    child_output(monkeypatch, video_result(duration=duration))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)


@pytest.mark.parametrize('rate', [True, False, None, '0/0', '1/0', '0/1', '-1/1', '121/1', float('nan'), float('inf')])
def test_video_rate_rejects_bool_zero_invalid_fraction_and_nonfinite(fake_mp4, fake_inspector, monkeypatch, rate):
    child_output(monkeypatch, video_result(stream={'avg_frame_rate': rate}))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)


@pytest.mark.parametrize('packets', [True, False, 1.9, 0, -1, float('nan'), float('inf'), 'invalid', None])
def test_video_packet_evidence_cannot_be_coerced_from_bool_or_fraction(fake_mp4, fake_inspector, monkeypatch, packets):
    child_output(monkeypatch, video_result(stream={'nb_read_packets': packets}))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)


@pytest.mark.parametrize('frames', [True, False, 1.9, 0, -1, float('nan'), float('inf'), 'invalid', None, '0', '1.0', '+1', [], {}])
def test_decoded_frame_count_requires_positive_integer_evidence(fake_mp4, fake_inspector, monkeypatch, frames):
    child_output(monkeypatch, video_result(stream={'nb_read_frames': frames}))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)


def test_partial_decoded_video_evidence_does_not_certify_complete_packets(fake_mp4, fake_inspector, monkeypatch):
    child_output(monkeypatch, video_result(stream={'nb_read_frames': '1', 'nb_read_packets': '2'}))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)


def test_declared_video_sample_count_must_match_decoded_and_observed_counts(fake_mp4, fake_inspector, monkeypatch):
    child_output(monkeypatch, video_result(stream={'nb_frames': '2', 'nb_read_frames': '1', 'nb_read_packets': '1'}))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)


def test_aac_priming_may_have_fewer_decoded_frames_than_complete_packets(fake_mp4, fake_inspector, monkeypatch):
    streams = video_result()['streams'] + [{'codec_type': 'audio', 'codec_name': 'aac', 'nb_frames': '48', 'nb_read_packets': '48', 'nb_read_frames': '47'}]
    child_output(monkeypatch, video_result(streams=streams))
    result = fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)
    assert result.codec_metadata == {'video_codec': 'h264', 'audio_codec': 'aac'}


def test_declared_audio_sample_count_must_match_observed_packets(fake_mp4, fake_inspector, monkeypatch):
    streams = video_result()['streams'] + [{'codec_type': 'audio', 'codec_name': 'aac', 'nb_frames': '48', 'nb_read_packets': '47', 'nb_read_frames': '46'}]
    child_output(monkeypatch, video_result(streams=streams))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)


def test_child_container_format_mismatch_cannot_certify_mp4(fake_mp4, fake_inspector, monkeypatch):
    child_output(monkeypatch, video_result(format_name='matroska,webm'))
    with pytest.raises(InspectionFailure):
        fake_inspector.inspect(fake_mp4, 'video/mp4', fake_mp4.stat().st_size)


def test_absent_inspectors_are_not_advertised(monkeypatch):
    monkeypatch.setattr(inspection.importlib.util, 'find_spec', lambda module: None)
    assert LocalInspector(MediaConfig()).available_mimes() == ()


def test_nonexecutable_video_inspector_is_not_advertised(tmp_path, monkeypatch):
    monkeypatch.setattr(inspection.importlib.util, 'find_spec', lambda module: None)
    broken = tmp_path / 'not-executable'
    broken.write_text('#!/bin/sh\nexit 2\n')
    assert LocalInspector(MediaConfig(ffprobe_path=str(broken))).available_mimes() == ()


def test_executable_but_broken_video_inspector_is_not_advertised(tmp_path, monkeypatch):
    monkeypatch.setattr(inspection.importlib.util, 'find_spec', lambda module: None)
    broken = tmp_path / 'broken-executable'
    broken.write_text('#!/bin/sh\nexit 2\n'); broken.chmod(0o700)
    assert 'video/mp4' not in LocalInspector(MediaConfig(ffprobe_path=str(broken))).available_mimes()


@pytest.fixture
def actual_mp4(tmp_path, readonly_real_child):
    ffmpeg = Path('/opt/homebrew/bin/ffmpeg')
    ffprobe = Path('/opt/homebrew/bin/ffprobe')
    if not ffmpeg.is_file() or not ffprobe.is_file():
        pytest.skip('Read-only installed ffmpeg/ffprobe unavailable')
    path = tmp_path / 'local-fixture.mp4'
    result = subprocess.run([str(ffmpeg), '-nostdin', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=16x16:r=2', '-t', '1', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path)], capture_output=True, timeout=15, check=False)
    assert result.returncode == 0, 'The installed encoder could not make an isolated H.264 fixture'
    return path


def test_actual_mp4_has_positive_inspected_evidence(actual_mp4):
    result = LocalInspector(MediaConfig(ffprobe_path='/opt/homebrew/bin/ffprobe')).inspect(actual_mp4, 'video/mp4', actual_mp4.stat().st_size)
    assert (result.width, result.height, result.mime_type) == (16, 16, 'video/mp4')
    assert 0 < result.duration_ms <= 120000 and 0 < result.frame_rate <= 120
    assert result.codec_metadata['video_codec'] == 'h264'


def test_actual_header_only_and_truncated_mp4_are_not_ready(fake_mp4, actual_mp4, tmp_path):
    broken = tmp_path / 'truncated.mp4'
    broken.write_bytes(actual_mp4.read_bytes()[:100])
    for path in (fake_mp4, broken):
        with pytest.raises(InspectionFailure):
            LocalInspector(MediaConfig(ffprobe_path='/opt/homebrew/bin/ffprobe')).inspect(path, 'video/mp4', path.stat().st_size)


def test_actual_corrupt_h264_packets_cannot_be_ready(actual_mp4, tmp_path):
    body = bytearray(actual_mp4.read_bytes())
    marker = body.find(b'mdat')
    assert marker >= 4 and marker + 4 < len(body)
    # Retain MP4 indexes and valid container metadata but destroy every coded
    # media packet. Counting demuxed packets is not proof they decode as H.264.
    body[marker + 4:] = b'\xff' * (len(body) - marker - 4)
    corrupt = tmp_path / 'corrupted-packets.mp4'
    corrupt.write_bytes(body)
    try:
        result = LocalInspector(MediaConfig(ffprobe_path='/opt/homebrew/bin/ffprobe')).inspect(corrupt, 'video/mp4', len(body))
    except InspectionFailure:
        return
    pytest.fail(f'Corrupt H.264 bytes returned ready metadata: {result!r}')


def packet_ranges(path, selection):
    result = subprocess.run(['/opt/homebrew/bin/ffprobe', '-v', 'error', '-select_streams', selection, '-show_packets', '-show_entries', 'packet=pos,size', '-of', 'json', str(path)], capture_output=True, timeout=5, check=False)
    assert result.returncode == 0, 'The installed parser could not enumerate fixture packets'
    return [(int(packet['pos']), int(packet['size'])) for packet in json.loads(result.stdout)['packets']]


@pytest.mark.parametrize('index', [0, -1])
def test_actual_one_corrupt_h264_packet_among_good_packets_is_not_ready(actual_mp4, tmp_path, index):
    body = bytearray(actual_mp4.read_bytes())
    packets = packet_ranges(actual_mp4, 'v:0')
    assert len(packets) >= 2
    start, size = packets[index]
    assert body[start:start + size]
    body[start:start + size] = b'\xff' * size
    path = tmp_path / f'one-bad-video-packet-{index}.mp4'
    path.write_bytes(body)
    with pytest.raises(InspectionFailure):
        LocalInspector(MediaConfig(ffprobe_path='/opt/homebrew/bin/ffprobe')).inspect(path, 'video/mp4', len(body))


def test_actual_missing_final_h264_packet_cannot_pass_after_a_good_first_frame(actual_mp4, tmp_path):
    packets = packet_ranges(actual_mp4, 'v:0')
    assert len(packets) >= 2
    body = actual_mp4.read_bytes()[:packets[-1][0]]
    path = tmp_path / 'missing-final-video-packet.mp4'
    path.write_bytes(body)
    try:
        result = LocalInspector(MediaConfig(ffprobe_path='/opt/homebrew/bin/ffprobe')).inspect(path, 'video/mp4', len(body))
    except InspectionFailure:
        return
    probe = subprocess.run(['/opt/homebrew/bin/ffprobe', '-v', 'error', '-count_frames', '-count_packets', '-show_entries', 'stream=nb_frames,nb_read_frames,nb_read_packets', '-of', 'json', str(path)], capture_output=True, timeout=5, check=False)
    pytest.fail(f'Missing final H.264 packet returned ready metadata: {result!r}; container counts: {probe.stdout.decode()}')


@pytest.fixture
def actual_av_mp4(tmp_path, readonly_real_child):
    path = tmp_path / 'local-video-audio-fixture.mp4'
    result = subprocess.run(['/opt/homebrew/bin/ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=16x16:r=2', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', '-movflags', '+faststart', str(path)], capture_output=True, timeout=15, check=False)
    assert result.returncode == 0, 'The installed encoder could not make an isolated H.264/AAC fixture'
    return path


def test_actual_h264_and_aac_have_positive_decoding_evidence(actual_av_mp4):
    result = LocalInspector(MediaConfig(ffprobe_path='/opt/homebrew/bin/ffprobe')).inspect(actual_av_mp4, 'video/mp4', actual_av_mp4.stat().st_size)
    assert result.codec_metadata == {'video_codec': 'h264', 'audio_codec': 'aac'}
    assert result.width == result.height == 16 and result.duration_ms > 0


def test_actual_corrupt_aac_with_good_h264_video_is_not_ready(actual_av_mp4, tmp_path):
    body = bytearray(actual_av_mp4.read_bytes())
    packets = packet_ranges(actual_av_mp4, 'a:0')
    assert len(packets) >= 3
    start, size = packets[len(packets) // 2]
    body[start:start + size] = b'\xff' * size
    path = tmp_path / 'one-bad-audio-packet.mp4'
    path.write_bytes(body)
    with pytest.raises(InspectionFailure):
        LocalInspector(MediaConfig(ffprobe_path='/opt/homebrew/bin/ffprobe')).inspect(path, 'video/mp4', len(body))


def test_actual_missing_final_aac_packet_cannot_pass_with_complete_good_video(actual_av_mp4, tmp_path):
    audio = packet_ranges(actual_av_mp4, 'a:0')
    video = packet_ranges(actual_av_mp4, 'v:0')
    assert len(audio) >= 3 and len(video) >= 2
    cutoff = audio[-1][0]
    assert all(start + size <= cutoff for start, size in video)
    body = actual_av_mp4.read_bytes()[:cutoff]
    path = tmp_path / 'missing-final-audio-packet.mp4'
    path.write_bytes(body)
    try:
        result = LocalInspector(MediaConfig(ffprobe_path='/opt/homebrew/bin/ffprobe')).inspect(path, 'video/mp4', len(body))
    except InspectionFailure:
        return
    probe = subprocess.run(['/opt/homebrew/bin/ffprobe', '-v', 'error', '-count_frames', '-count_packets', '-show_entries', 'stream=codec_type,nb_frames,nb_read_frames,nb_read_packets', '-of', 'json', str(path)], capture_output=True, timeout=5, check=False)
    pytest.fail(f'Missing final AAC packet returned ready metadata: {result!r}; container counts: {probe.stdout.decode()}')
