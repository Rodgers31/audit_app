"""Whitelisted workflow selection; execution still uses the native CLI owner.

This plan is independent of the UI publication calendar. It does not certify
source freshness and it is not a no-write preflight (operational receipts write).
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys

from .registries import _BUILTIN_DOMAIN_PACKAGES

LEGACY_DOMAINS = tuple(sorted(p.rsplit('.', 1)[1] for p in _BUILTIN_DOMAIN_PACKAGES))
DAILY = '0 2 * * 1-6'
WEEKLY = '0 3 * * 0'


def boolean(value):
    if type(value) is not str or value not in ('true', 'false'):
        raise ValueError('Source plan flags require literal true or false')
    return value == 'true'


@dataclass(frozen=True)
class SourcePlan:
    domains: tuple[str, ...]
    bootstrap: bool
    dry_run: bool

    @property
    def argv(self):
        validate_plan(self)
        args = [sys.executable, '-m', 'seeding.cli', 'seed']
        for domain in self.domains:
            args.extend(['--domain', domain])
        return [*args, '--dry-run' if self.dry_run else '--no-dry-run']


def build_plan(*, event, schedule, domain, dry_run, cra, opendata, discovery,
               bootstrap='false'):
    enabled = {'cra': boolean(cra), 'opendata': boolean(opendata)}
    discover = boolean(discovery)
    if discover and not enabled['opendata']:
        raise ValueError('KNBS discovery requires the OpenData opt-in too')
    dry = boolean(dry_run)
    boot = boolean(bootstrap)
    if type(domain) is not str or domain not in ('', *LEGACY_DOMAINS, 'cra', 'opendata'):
        raise ValueError('Unknown source plan domain')
    if event == 'schedule':
        if schedule not in (DAILY, WEEKLY) or domain or dry or boot:
            raise ValueError('Unsupported scheduled source plan')
        weekly = schedule == WEEKLY
        # Admit explicit opt-ins before legacy work can consume the shared
        # native budget. This is priority, not a completion/capacity promise;
        # the unchanged CLI records and fails any remaining budget drop.
        domains = (*(d for d, on in enabled.items() if weekly and on), *LEGACY_DOMAINS)
        return SourcePlan(domains, weekly, False)
    if event != 'workflow_dispatch' or schedule != '':
        raise ValueError('Unsupported source plan event')
    if domain in enabled and not enabled[domain]:
        raise ValueError('Selected source requires its explicit opt-in')
    domains = (domain,) if domain else (*(d for d, on in enabled.items() if on), *LEGACY_DOMAINS)
    return SourcePlan(domains, boot, dry)


def environment_plan():
    return build_plan(event=os.environ['SEED_PLAN_EVENT'],
        schedule=os.environ.get('SEED_PLAN_SCHEDULE', ''),
        domain=os.environ.get('SEED_PLAN_DOMAIN', ''),
        dry_run=os.environ.get('SEED_PLAN_DRY_RUN') or 'false',
        bootstrap=os.environ.get('SEED_PLAN_BOOTSTRAP') or 'false',
        cra=os.environ.get('SEED_CRA_INGESTION_ENABLED', 'false'),
        opendata=os.environ.get('SEED_OPENDATA_INGESTION_ENABLED', 'false'),
        discovery=os.environ.get('SEED_KNBS_RELEASE_DISCOVERY_ENABLED', 'false'))


def validate_plan(plan):
    """Guard both direct invocation and Actions output publication."""
    if (type(plan) is not SourcePlan or type(plan.domains) is not tuple
            or not 1 <= len(plan.domains) <= len(LEGACY_DOMAINS) + 2
            or any(type(d) is not str or d not in (*LEGACY_DOMAINS, 'cra', 'opendata') for d in plan.domains)
            or len(set(plan.domains)) != len(plan.domains)
            or type(plan.bootstrap) is not bool or type(plan.dry_run) is not bool):
        raise ValueError('Invalid source plan output or invocation')


def write_plan_outputs(plan):
    """Publish selection only to this Actions step's precreated output file."""
    validate_plan(plan)
    if 'GITHUB_OUTPUT' not in os.environ:
        return
    path = Path(os.environ['GITHUB_OUTPUT'])
    root = Path(__file__).resolve().parents[2]
    if (not path.is_file() or path.is_symlink() or path.resolve().is_relative_to(root)
            or path.stat().st_size > 64 * 1024):
        raise ValueError('Source plan output must be an external Actions output file')
    # All values derive from the whitelist/literal validators, never raw input.
    with path.open('a', encoding='utf-8') as output:
        output.write('domains=' + json.dumps(plan.domains, separators=(',', ':')) + '\n')
        output.write('bootstrap=' + ('true' if plan.bootstrap else 'false') + '\n')


def main():
    try:
        if sys.argv[1:] not in (['--check'], ['--execute']):
            raise ValueError('Expected --check or --execute')
        plan = environment_plan()
        if sys.argv[1] == '--check':
            write_plan_outputs(plan)
        print(json.dumps({'domains': plan.domains, 'bootstrap': plan.bootstrap,
                          'dry_run': plan.dry_run, 'evidence': 'selection_plan_only'}), flush=True)
        if sys.argv[1] == '--execute':
            return subprocess.run(plan.argv, check=False).returncode
        return 0
    except (KeyError, ValueError) as exc:
        print('Source plan refused: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
