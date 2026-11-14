"""Build the selected health probe inputs inside the job that uses them."""

import os
from pathlib import Path
import sys

from .current_run import plan_identity
from .source_plan import environment_plan, health_source_lines


def prepare():
    plan = environment_plan()
    if (not os.environ.get('GITHUB_SHA')
            or os.environ['GITHUB_SHA'] != os.environ['HC_SOURCE_SHA']
            or plan_identity(plan) != os.environ['HC_PLAN_SHA']):
        raise ValueError('Health selection does not match the upstream plan')

    inventory = health_source_lines(plan)
    runner_temp = Path(os.environ['RUNNER_TEMP'])
    if not runner_temp.is_absolute() or runner_temp.is_symlink() or not runner_temp.is_dir():
        raise ValueError('Health runner temp directory refused')
    path = runner_temp / 'seed-health-inventory'
    # A private, fresh file on this runner only. Never publish URL bytes in
    # Actions outputs, artifacts, summaries or diagnostics.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(inventory + '\n')


def main():
    try:
        prepare()
    except (ValueError, OSError, KeyError, SyntaxError):
        # Do not log exception text: it can contain rejected secret settings.
        print('Selected health inventory could not be verified or prepared', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
