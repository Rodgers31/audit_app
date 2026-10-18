"""Isolated card/video producer. Input is a validated composition, never media paths.

Invoked with -I. No provider transport, shell, remote URLs, supplied font/filter
expressions or executable templates. OS limits also bound an orphan after SIGKILL.
"""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import textwrap
import threading
import time


def main():
    signal.signal(signal.SIGALRM, lambda *_: os.killpg(os.getpgrp(), signal.SIGKILL))
    signal.alarm(120)
    resource.setrlimit(resource.RLIMIT_CPU, (110, 115))
    resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    # Linux additionally supports a reliable total address-space ceiling.
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    def monitor_memory():
        # macOS does not implement a usable RLIMIT_DATA/AS. A private process
        # group census bounds aggregate RSS (sampled every 200 ms) on both OSes.
        # Failure to inspect is refusal, never unlimited execution.
        while True:
            try:
                result = subprocess.run(['/bin/ps', '-o', 'rss=', '-g', str(os.getpgrp())], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=1, check=True)
                rss = [int(v) for v in result.stdout.split()]
                if not rss or sum(rss) > 512 * 1024:
                    raise ValueError('Memory census exceeded')
            except Exception:
                os.killpg(os.getpgrp(), signal.SIGKILL)
            time.sleep(0.2)
    threading.Thread(target=monitor_memory, daemon=True).start()
    from PIL import Image, ImageDraw, ImageFont
    work, ffmpeg = Path(sys.argv[1]), sys.argv[2]
    spec = json.loads((work / 'input.json').read_text())
    font = ImageFont.load_default(size=30)
    small = ImageFont.load_default(size=22)
    facts = {f['id']: f for f in spec['facts']}
    captions, transcript, elapsed = [], [], 0
    for index, scene in enumerate(spec['scenes']):
        fact = facts[scene['fact_id']]
        image = Image.new('RGB', (720, 1280), '#f7f7f5')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 720, 20), fill='#12694d')
        draw.text((48, 80), 'AuditGava | ' + spec['template'].replace('_', ' '), fill='#12694d', font=small)
        draw.multiline_text((48, 170), '\n'.join(textwrap.wrap(spec['title'], 28)), fill='#18251f', font=font, spacing=14)
        if spec['kind'] == 'graphic':
            for fact_index, card_fact in enumerate(spec['facts']):
                y = 380 + fact_index * (680 // len(spec['facts']))
                draw.text((48, y), card_fact['id'].replace('_', ' '), fill='#12694d', font=small)
                draw.multiline_text((48, y + 35), '\n'.join(textwrap.wrap(card_fact['text'], 42)), fill='#18251f', font=small, spacing=6)
        else:
            draw.multiline_text((48, 440), '\n'.join(textwrap.wrap(fact['text'], 29)), fill='#18251f', font=font, spacing=14)
        draw.text((48, 1120), 'Fact: ' + fact['id'], fill='#18251f', font=small)
        draw.text((48, 1190), f'Card {index + 1}/{len(spec["scenes"])} | template v1', fill='#18251f', font=small)
        image.save(work / f'card-{index}.png', optimize=False, compress_level=9)
        def stamp(seconds):
            return f'00:00:{seconds:02d},000'
        captions.append(f'{index + 1}\n{stamp(elapsed)} --> {stamp(elapsed + scene["seconds"])}\n{fact["text"]}\n')
        transcript.append({'fact_id': fact['id'], 'source_url': fact['source_url'], 'start_ms': elapsed * 1000, 'end_ms': (elapsed + scene['seconds']) * 1000, 'text': fact['text']})
        elapsed += scene['seconds']
    (work / 'captions.srt').write_text('\n'.join(captions))
    (work / 'transcript.json').write_text(json.dumps(transcript, sort_keys=True))
    if spec['kind'] == 'graphic':
        return
    # The concat manifest consists only of generated constant filenames.
    entries = []
    for index, scene in enumerate(spec['scenes']):
        entries.extend([f"file 'card-{index}.png'", f'duration {scene["seconds"]}'])
    entries.append(f"file 'card-{len(spec['scenes']) - 1}.png'")
    (work / 'frames.txt').write_text('\n'.join(entries) + '\n')
    command = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-n', '-threads', '1', '-filter_threads', '1', '-protocol_whitelist', 'file,pipe', '-f', 'concat', '-safe', '1', '-i', 'frames.txt', '-map', '0:v:0', '-vf', 'fps=24,format=yuv420p', '-c:v', 'libx264', '-threads', '1', '-preset', 'ultrafast', '-crf', '24', '-t', str(elapsed), '-map_metadata', '-1', '-fflags', '+bitexact', '-flags:v', '+bitexact', '-movflags', '+faststart', 'output.mp4']
    subprocess.run(command, cwd=work, check=True, timeout=100, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})


if __name__ == '__main__':
    main()
