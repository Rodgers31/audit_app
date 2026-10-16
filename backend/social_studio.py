"""Explicit one-job local operator entrypoint. Never starts a scheduler or uploads."""
import argparse
from pathlib import Path
from uuid import UUID

from social.studio.runner import recover_interrupted, run_job
from social.studio.runtime import StudioRuntime


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('render', 'recover'))
    parser.add_argument('job_id', type=UUID)
    parser.add_argument('--enable-local-rendering', action='store_true')
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--ffprobe', required=True)
    args = parser.parse_args(argv)
    runtime = StudioRuntime(args.enable_local_rendering, args.root, args.ffmpeg, args.ffprobe).require()
    # Reuse the application DB configuration only after all local guards pass.
    from database import SessionLocal
    if args.operation == 'render':
        state = run_job(SessionLocal, runtime, args.job_id)
        print('render state:', state)
        return 0 if state == 'ready' else 1
    recover_interrupted(SessionLocal, args.job_id)
    print('interrupted execution marked failed; no automatic retry')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
