"""Bounded isolated tool entry point. No application imports or credentials."""
import json
import os
from pathlib import Path
import resource
import sys


def main():
    kind, filename, ffprobe = sys.argv[1:4]
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024, 64 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    # RLIMIT_AS is enforced on Linux; macOS applies inconsistent VM accounting.
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    if kind == 'image':
        from PIL import Image
        import warnings
        Image.MAX_IMAGE_PIXELS = 16_000_000
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(filename) as image:
            mime = {'JPEG': 'image/jpeg', 'PNG': 'image/png'}.get(image.format)
            if not mime or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Unsupported or animated image')
            image.verify()
        with Image.open(filename) as image:
            image.load()
            print(json.dumps({'mime_type': mime, 'width': image.width, 'height': image.height, 'duration_ms': None, 'frame_rate': None, 'codec_metadata': {}}))
    elif kind == 'video':
        # A local MP4 only. Network/container playlists and unrelated demuxers
        # are unavailable; no shell interpolation or rendering/transcoding.
        # Replace this same process, so the parent timeout kills the decoder
        # itself and cannot leave a nested ffprobe process running.
        os.execv(ffprobe, [ffprobe, '-v', 'error', '-err_detect', 'explode', '-threads', '1', '-protocol_whitelist', 'file', '-max_alloc', '67108864', '-f', 'mov', '-enable_drefs', '0', '-use_absolute_path', '0', '-count_packets', '-count_frames', '-show_entries', 'format=format_name,duration:stream=codec_type,codec_name,width,height,avg_frame_rate,nb_frames,nb_read_packets,nb_read_frames', '-of', 'json', '-i', str(Path(filename).resolve())])
    else:
        raise ValueError('Unsupported inspection')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        sys.exit(2)
