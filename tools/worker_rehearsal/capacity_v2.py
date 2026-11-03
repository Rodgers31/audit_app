"""Trusted entry point for unauthenticated offline V2 telemetry assessment.

The caller must establish this loader's identity independently. The returned
assessor hash identifies the implementation bytes compiled below, not this
loader, a Python bytecode cache, the caller or an authenticated runtime.
Historical producers remain unchanged and still use V1.
"""
from pathlib import Path


def _load_assessor():
    path = Path(__file__).with_name('capacity_v2_assessor.py')
    source = path.read_bytes()
    namespace = {'__name__': '_worker_capacity_v2_assessor', '__file__': str(path),
                 '_ASSESSOR_SOURCE_BYTES': source}
    exec(compile(source, str(path), 'exec', dont_inherit=True), namespace)
    return namespace['assess']


assess = _load_assessor()
