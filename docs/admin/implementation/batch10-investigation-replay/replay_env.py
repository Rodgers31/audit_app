"""Explicit inert runtime inputs for new executions, never archived producers."""
import os
from pathlib import Path
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def external_output(root, output):
    original = Path(output)
    require(not original.is_symlink(), 'output symlink refused')
    out = original.resolve()
    require(out.is_dir() and not out.is_relative_to(root) and not root.is_relative_to(out),
            'existing external output directory required')
    return out


def refuse_dotenv(*directories):
    for directory in directories:
        for path in Path(directory).glob('.env*'):
            if path.name.endswith(('.example', '.sample', '.template')):
                continue  # Documented templates are not runtime dotenv inputs.
            require(False, 'dotenv input refused: ' + str(path))


def child_environment(workspace, executable):
    """No inherited variables, PATH entries, home, npm config, loader, or proxies."""
    work = Path(workspace)
    work.mkdir()
    home, temp = work / 'home', work / 'tmp'
    home.mkdir()
    temp.mkdir()
    binary = Path(executable).resolve()
    require(binary.is_file() and os.access(binary, os.X_OK), 'absolute executable required')
    paths = dict.fromkeys([str(binary.parent), str(Path(sys.executable).resolve().parent), *os.defpath.split(os.pathsep)])
    return {
        'PATH': os.pathsep.join(paths), 'HOME': str(home), 'TMPDIR': str(temp),
        'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1',
        'NEXT_PUBLIC_API_URL': 'http://127.0.0.1:18014', 'INTERNAL_API_URL': 'http://127.0.0.1:18014',
        'NEXT_PUBLIC_SUPABASE_URL': 'http://127.0.0.1:18014',
        'NEXT_PUBLIC_SUPABASE_ANON_KEY': 'batch10-current-replay-inert-anon-key',
        'NEXT_TELEMETRY_DISABLED': '1', 'ONNXRUNTIME_NODE_INSTALL': 'skip',
        'NATIVE_VERIFY_CACHE_DIR': str(work / 'model-cache'), 'npm_config_cache': str(work / 'npm-cache'),
        'npm_config_userconfig': os.devnull, 'npm_config_globalconfig': os.devnull,
        'npm_config_engine_strict': 'true',
    }
