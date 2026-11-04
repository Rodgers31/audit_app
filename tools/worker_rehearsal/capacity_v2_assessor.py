"""Internal numerical implementation; the public loader alone stamps identity.

Direct execution exposes only unqualified calculations, never a V2 identity or
acceptance result. Existing run.py/bounded.py still use V1. A future producer or
explicit offline reassessment must use the externally trusted capacity_v2 API.
"""
import hashlib
import re
from pathlib import Path
from types import MappingProxyType


_ARCHIVES = MappingProxyType({
    'qualification.py': 'd2b02ce6fe9f0766d73c99a59f6b1fa21ea62c1b02615054bfd55dc7a916bacc',
    'run.py': 'e883c6b34399bbcb270d51e94e86371146583cfc6bd01a2976d731b2c5e685bf',
})


def _archived(name):
    path = Path(__file__).with_name(name)
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != _ARCHIVES[name]:
        raise ValueError('Archived capacity dependency changed; versioned review required')
    # Compile the verified bytes: reopening this path could execute a different
    # file after the hash check. No module import/cache or main entry is needed.
    namespace = {'__name__': '_worker_capacity_archive', '__file__': str(path)}
    exec(compile(source, str(path), 'exec', dont_inherit=True), namespace)
    return namespace


_LEGACY = _archived('qualification.py')
_PROFILE = MappingProxyType(dict(_archived('run.py')['THRESHOLDS']))
_MAXIMUM_GAP_SECONDS = 15


def _operations(requests, cohort, targets, wire_before, wire_after):
    """Account for every emitted event, including reads that never completed.

    The frozen V1 calculation selects only mutations and image downloads. An
    endpoint refusal emits a start without a completion, so filtering first
    would discard the evidence of a failed operation. These are the inert
    fixture's routes, not permission to contact the corresponding providers.
    """
    require = _LEGACY['require']
    require(type(requests) is list and requests, 'Missing operation inventory')
    require(type(cohort) is dict, 'Missing operation cohort')
    for key in ('media_paths', 'provider_paths'):
        require(type(cohort.get(key)) is list and cohort[key]
                and all(type(path) is str for path in cohort[key]),
                'Missing operation path inventory')
    # The current producer binds its native cohort target to one account's
    # Graph routes. It does not emit an account-to-route mapping for arbitrary
    # additional accounts. Preserve that exact association; ambiguous multiple
    # Graph scopes cannot be inferred by multiplying route roots and saved IDs.
    graph_scopes = set()
    for path in cohort['provider_paths']:
        match = re.fullmatch(r'(/v[0-9]+\.[0-9]+/)([0-9]+)/(?:feed|photos)', path)
        if match:
            graph_scopes.add((match[1], match[2]))
    require(len(graph_scopes) <= 1, 'Ambiguous Graph account/version association')
    native = [target for target in targets if target['id'] == cohort.get('target_id')]
    require(len(native) == 1, 'Missing selected operation target')
    selected_account = native[0].get('account_id')
    identities = {}
    for target in targets:
        values = [target.get('primary_remote_id')]
        by_kind = {'post_id': set(), 'photo_id': set()}
        for key in ('remote_refs', 'checkpoint'):
            saved = target.get(key)
            require(saved is None or type(saved) is dict, 'Malformed saved remote identities')
            if saved is not None:
                values.extend(saved.get(key) for key in ('post_id', 'photo_id'))
                for kind in by_kind:
                    if saved.get(kind) is not None:
                        require(type(saved[kind]) is str, 'Malformed saved remote identity')
                        by_kind[kind].add(saved[kind])
        require(all(len(ids) <= 1 for ids in by_kind.values()),
                'Conflicting saved remote identities for one target')
        if by_kind['post_id'] and target.get('primary_remote_id') is not None:
            require(target['primary_remote_id'] in by_kind['post_id'],
                    'Primary and saved post identities conflict')
        for value in values:
            if value is not None:
                require(type(value) is str and re.fullmatch(r'[0-9]+(?:_[0-9]+)?', value),
                        'Malformed saved remote identity')
                account = target.get('account_id')
                require(type(account) is str and account, 'Saved remote account identity absent')
                owner = (target['id'], account)
                require(value not in identities or identities[value] == owner,
                        'Conflicting saved remote identity ownership')
                identities[value] = owner
    confirmations = set()
    if graph_scopes:
        root, external_account = next(iter(graph_scopes))
        require(type(selected_account) is str and selected_account,
                'Selected Graph account identity absent')
        for remote_id, (_, account) in identities.items():
            if account == selected_account:
                require('_' not in remote_id or remote_id.split('_', 1)[0] == external_account,
                        'Saved remote identity names another Graph account')
                confirmations.add(root + remote_id)
    starts, completions = [], []
    for row in requests:
        require(type(row) is dict, 'Malformed operation event')
        method, path = row.get('method'), row.get('path')
        require(type(method) is str and method in {'POST', 'GET', 'HEAD'}
                and type(path) is str, 'Unexpected operation method/path')
        allowed = (path in cohort['provider_paths'] if method == 'POST' else
                   path in cohort['media_paths'] or method == 'GET' and
                   (path == '/rest/v1/profiles' or path in confirmations))
        require(allowed, 'Unaccounted operation route')
        require(('started' in row) != ('completed' in row),
                'Operation event must contain exactly one phase')
        for key in ('input_bytes', 'output_bytes'):
            if key in row:
                _LEGACY['integer'](row[key])
        (starts if 'started' in row else completions).append(row)
    pairs = _LEGACY['pairs'](starts, completions,
        _LEGACY['number'](wire_before.get('measurement_started'), positive=True),
        _LEGACY['number'](wire_after.get('measurement_completed'), positive=True))
    require(all(start['method'] == end['method'] for start, end in pairs),
            'Operation method changed between phases')
    return len(pairs)


def assess(samples, latencies, census, wire_before, wire_after, requests, duration, thresholds):
    """Apply the frozen workload contract plus bounded observation gaps.

    Raises on incomplete or malformed telemetry. Even a successful assessment is
    an unauthenticated offline interpretation, not intended-host qualification.
    No processes, database connections, network calls or receipt files are made.
    """
    require, number, integer = _LEGACY['require'], _LEGACY['number'], _LEGACY['integer']
    require(type(thresholds) is dict and set(thresholds) == set(_PROFILE),
            'Exact fixed capacity profile required')
    require(all(type(thresholds[key]) is type(value) and thresholds[key] == value
                for key, value in _PROFILE.items()), 'Exact fixed capacity profile required')
    require(180 <= number(duration, positive=True) <= 900, 'Duration must be 180..900 seconds')
    require(type(samples) is list and len(samples) >= 20, 'Insufficient cgroup samples')
    previous, maximum_gap = None, 0
    for sample in samples:
        require(type(sample) is dict, 'Invalid cgroup sample')
        elapsed = number(sample.get('elapsed'), positive=True)
        require(elapsed <= duration, 'Cgroup sample outside measured duration')
        if previous is not None:
            gap = elapsed - previous
            require(0 < gap <= _MAXIMUM_GAP_SECONDS, 'Cgroup observation gap exceeds 15 seconds or is nonmonotonic')
            maximum_gap = max(maximum_gap, gap)
        previous = elapsed
        processes = sample.get('processes')
        require(type(processes) is list and processes, 'Missing actual process census')
        pids = []
        for process in processes:
            require(type(process) is dict, 'Invalid process census')
            pids.append(integer(process.get('pid'), positive=True))
        require(len(pids) == len(set(pids)), 'Duplicate process identity')
    require(type(census) is dict and type(census.get('social_post_targets')) is list,
            'Missing native workload census')
    targets = census['social_post_targets']
    require(all(type(row) is dict and type(row.get('id')) is str and row['id']
                for row in targets), 'Target identity absent')
    require(len({row['id'] for row in targets}) == len(targets), 'Duplicate target identity')
    require(type(wire_before) is dict and type(wire_after) is dict,
            'Missing operation measurement window')
    operations = _operations(requests, census.get('cohort'), targets, wire_before, wire_after)
    result = _LEGACY['assess'](samples, latencies, census, wire_before, wire_after,
                               requests, duration, dict(_PROFILE))
    return dict(api_p95=result['api_p95'], mean_cpu=result['mean_cpu'],
                published=result['published'], server_bytes=result['server_bytes'],
                client_bytes=result['client_bytes'], provider_mutations=result['provider_mutations'],
                sql_calls=result['sql_calls'], maximum_sample_gap_seconds=maximum_gap,
                observed_operations=operations,
                maximum_allowed_sample_gap_seconds=_MAXIMUM_GAP_SECONDS)
