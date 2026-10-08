"""Actual local byte inspection; all external output is treated as untrusted."""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


class InspectionFailure(Exception):
    pass


@dataclass(frozen=True)
class InspectedMedia:
    mime_type: str
    byte_size: int
    sha256: str
    width: int
    height: int
    duration_ms: int | None
    frame_rate: float | None
    codec_metadata: dict


def count(value):
    if type(value) is int and value > 0: return value
    if isinstance(value, str) and re.fullmatch('[1-9][0-9]{0,8}', value): return int(value)
    raise InspectionFailure('Invalid decoded media evidence')


class LocalInspector:
    def __init__(self, config):
        self.config = config.validate()
        # shutil.which() returns None when no executable is installed. This
        # disables video alone and keeps the image child's argument a string.
        self._ffprobe_path = self.config.ffprobe_path or ''
        self._available = None

    def available_mimes(self):
        if self._available is not None: return self._available
        images, videos = (), ()
        try:
            if importlib.util.find_spec('PIL'):
                from PIL import Image
                Image.init()
                if {'JPEG', 'PNG'} <= Image.OPEN.keys(): images = ('image/jpeg', 'image/png')
        except (ImportError, OSError): pass
        if self._ffprobe_path:
            try:
                path = Path(self._ffprobe_path)
                if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
                    self._available = images
                    return self._available
                with tempfile.TemporaryFile() as output:
                    result = subprocess.run([str(path), '-version'], stdout=output, stderr=subprocess.DEVNULL, timeout=2, check=False, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
                    output.seek(0)
                    if result.returncode == 0 and output.read(16).startswith(b'ffprobe version '): videos = ('video/mp4',)
            except (OSError, ValueError, subprocess.TimeoutExpired): pass
        self._available = images + videos
        return self._available

    def inspect(self, path: Path, declared_mime: str, expected_size: int):
        try:
            return self._inspect(path, declared_mime, expected_size)
        except InspectionFailure: raise
        except (ValueError, KeyError, TypeError, AttributeError, OSError, ArithmeticError, subprocess.TimeoutExpired):
            raise InspectionFailure('Media inspection failed or exceeded its resource limits') from None

    def _inspect(self, path, declared_mime, expected_size):
        if declared_mime not in self.available_mimes():
            raise InspectionFailure('Required inspection capability is unavailable')
        maximum = self.config.max_video_bytes if declared_mime == 'video/mp4' else self.config.max_image_bytes
        size = path.stat().st_size
        if type(expected_size) is not int or size != expected_size or not 0 < size <= maximum:
            raise InspectionFailure('Uploaded file length is invalid')
        digest = hashlib.sha256()
        with path.open('rb') as source:
            magic = source.read(32); digest.update(magic)
            for chunk in iter(lambda: source.read(256 * 1024), b''): digest.update(chunk)
        video = declared_mime == 'video/mp4'
        if video and (magic[4:8] != b'ftyp' or magic[8:12] not in {b'isom', b'iso2', b'iso6', b'mp41', b'mp42', b'avc1', b'dash', b'M4V '}):
            raise InspectionFailure('Actual bytes are not supported MP4 media')
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            result = subprocess.run([sys.executable, '-B', '-I', str(Path(__file__).with_name('inspection_child.py')), 'video' if video else 'image', str(path.resolve()), self._ffprobe_path if video else ''], stdout=output, stderr=errors, timeout=self.config.inspection_timeout, check=False, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            output.seek(0); raw = output.read(64 * 1024 + 1)
            errors.seek(0)
            if result.returncode != 0 or errors.read(1) or len(raw) > 64 * 1024:
                raise InspectionFailure('Media inspection failed or exceeded its resource limits')
            data = json.loads(raw)
        if not isinstance(data, dict): raise InspectionFailure('Invalid media tool output')
        if video:
            streams = data['streams']
            if not isinstance(streams, list) or not 1 <= len(streams) <= 4 or any(not isinstance(s, dict) for s in streams) or data['format']['format_name'] != 'mov,mp4,m4a,3gp,3g2,mj2':
                raise InspectionFailure('Unsupported video stream structure')
            pictures = [s for s in streams if s.get('codec_type') == 'video']
            if len(pictures) != 1 or pictures[0].get('codec_name') != 'h264' or any(s.get('codec_type') not in {'video', 'audio'} or s.get('codec_type') == 'audio' and s.get('codec_name') != 'aac' for s in streams):
                raise InspectionFailure('Supported video requires H.264 and optional AAC audio')
            stream = pictures[0]
            # Count decoded frames as well as packets. No errors were permitted
            # by the child; positive demuxed packets alone prove no decoding.
            for s in streams:
                count(s['nb_read_packets']); count(s['nb_read_frames'])
                if count(s['nb_frames']) != count(s['nb_read_packets']):
                    raise InspectionFailure('Media samples are incomplete')
            if not count(stream['nb_frames']) == count(stream['nb_read_frames']) == count(stream['nb_read_packets']):
                raise InspectionFailure('Video frames did not decode completely')
            raw_duration, raw_rate = data['format']['duration'], stream['avg_frame_rate']
            if type(raw_duration) not in {int, float, str} or not isinstance(raw_rate, str) or not re.fullmatch('[0-9]{1,8}/[1-9][0-9]{0,8}', raw_rate):
                raise InspectionFailure('Invalid video timing evidence')
            duration, rate = float(raw_duration), float(Fraction(raw_rate))
            if not math.isfinite(duration) or not 0 < duration <= 120 or not math.isfinite(rate) or not 0 < rate <= 120:
                raise InspectionFailure('Video duration or frame rate is unsupported')
            data = {'mime_type': 'video/mp4', 'width': stream['width'], 'height': stream['height'], 'duration_ms': max(1, round(duration * 1000)), 'frame_rate': rate, 'codec_metadata': {'video_codec': 'h264', 'audio_codec': 'aac' if any(s['codec_type'] == 'audio' for s in streams) else None}}
        elif set(data) != {'mime_type', 'width', 'height', 'duration_ms', 'frame_rate', 'codec_metadata'} or data['duration_ms'] is not None or data['frame_rate'] is not None or data['codec_metadata'] != {}:
            raise InspectionFailure('Invalid image tool metadata')
        width, height = data['width'], data['height']
        if data['mime_type'] != declared_mime or type(width) is not int or type(height) is not int or not 0 < width <= 10000 or not 0 < height <= 10000 or width * height > 16_000_000:
            raise InspectionFailure('Actual media type or dimensions do not match supported intake')
        return InspectedMedia(data['mime_type'], size, digest.hexdigest(), width, height, data['duration_ms'], data['frame_rate'], data['codec_metadata'])
