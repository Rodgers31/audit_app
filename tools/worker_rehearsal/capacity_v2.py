"""Trusted entry point for unauthenticated offline V2 telemetry assessment.

The caller must establish this loader's identity independently. The returned
assessor hash identifies the implementation bytes compiled below, not this
loader, a Python bytecode cache, the caller or an authenticated runtime.
Historical producers remain unchanged and still use V1.
"""
from functools import wraps
import hashlib
from pathlib import Path


def _load_assessor():
    path = Path(__file__).with_name('capacity_v2_assessor.py')
    source = path.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    namespace = {'__name__': '_worker_capacity_v2_assessor', '__file__': str(path)}
    exec(compile(source, str(path), 'exec', dont_inherit=True), namespace)
    implementation = namespace['assess']
    archives = dict(namespace['_ARCHIVES'])

    def unchanged():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Loaded assessor source changed')

    @wraps(implementation)
    def assess(samples, latencies, census, wire_before, wire_after, requests, duration, thresholds):
        unchanged()
        result = implementation(samples, latencies, census, wire_before, wire_after,
                                requests, duration, thresholds)
        unchanged()
        return dict(result, assessment_version=2, evidence_authenticated=False,
                    production_accepted=False, scope='operator-supplied offline telemetry',
                    assessor_sha256=digest, assessor_entrypoint='capacity_v2_assessor.py',
                    source_identity_scope='implementation bytes compiled by externally trusted capacity_v2.py',
                    archived_dependency_sha256=dict(archives))

    return assess


assess = _load_assessor()
