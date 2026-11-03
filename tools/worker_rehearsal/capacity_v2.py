"""Offline V2 telemetry assessment; archived producers remain unchanged.

This consumes operator-supplied observations. It authenticates no runtime and
never authorizes production. Existing run.py/bounded.py still use V1. A future
producer or explicit offline reassessment must call this API to obtain V2 bounds.
"""
import hashlib
from pathlib import Path
from types import MappingProxyType


_SOURCE_PATH = Path(__file__)
_LOADED_ASSESSOR_SHA256 = hashlib.sha256(_SOURCE_PATH.read_bytes()).hexdigest()
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


def _check_loaded_source():
    if hashlib.sha256(_SOURCE_PATH.read_bytes()).hexdigest() != _LOADED_ASSESSOR_SHA256:
        raise ValueError('Loaded assessor source changed')


def assess(samples, latencies, census, wire_before, wire_after, requests, duration, thresholds):
    """Apply the frozen workload contract plus bounded observation gaps.

    Raises on incomplete or malformed telemetry. Even a successful assessment is
    an unauthenticated offline interpretation, not intended-host qualification.
    No processes, database connections, network calls or receipt files are made.
    """
    _check_loaded_source()
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
    result = _LEGACY['assess'](samples, latencies, census, wire_before, wire_after,
                               requests, duration, dict(_PROFILE))
    _check_loaded_source()
    return dict(result, assessment_version=2, evidence_authenticated=False,
                production_accepted=False, scope='operator-supplied offline telemetry',
                maximum_sample_gap_seconds=maximum_gap,
                maximum_allowed_sample_gap_seconds=_MAXIMUM_GAP_SECONDS,
                assessor_sha256=_LOADED_ASSESSOR_SHA256,
                archived_dependency_sha256=dict(_ARCHIVES))
