"""Read-only Git/blob reconciliation; never runs tests or authorizes production."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
LIMIT = 512 * 1024


class Refused(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def read_json(path):
    try:
        with path.open('rb') as source:
            raw = source.read(LIMIT + 1)
    except OSError:
        raise Refused('SOURCE_RECEIPT_MISSING') from None
    return parse_json(raw)


def parse_json(raw):
    require(len(raw) <= LIMIT, 'SOURCE_RECEIPT_TOO_LARGE')
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('SOURCE_RECEIPT_INVALID_JSON') from None


def relative(value):
    require(type(value) is str and 0 < len(value) < 500, 'INVALID_SOURCE_PATH')
    path = PurePosixPath(value)
    require(not path.is_absolute() and str(path) == value and
            all(part not in {'.', '..', '.git'} for part in path.parts) and
            not any(ord(c) < 32 or ord(c) == 127 for c in value), 'INVALID_SOURCE_PATH')
    return value


def git(root, *arguments):
    result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True, timeout=15)
    require(result.returncode == 0, 'GIT_SOURCE_UNAVAILABLE')
    return result.stdout


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_entry(root, commit, name):
    # Only a successful empty tree lookup proves an absent companion file.
    # A Git error is never evidence of absence.
    raw = git(root, '--literal-pathspecs', 'ls-tree', '-z', commit, '--', name)
    if not raw:
        return None
    records = raw.rstrip(b'\0').split(b'\0')
    require(len(records) == 1, 'SOURCE_PATH_NOT_REGULAR_BLOB')
    header, separator, stored_path = records[0].partition(b'\t')
    fields = header.split()
    require(separator and stored_path == name.encode('utf-8') and len(fields) == 3 and
            fields[0] in (b'100644', b'100755') and fields[1] == b'blob', 'SOURCE_PATH_NOT_REGULAR_BLOB')
    return fields[2].decode('ascii')


def blob(root, commit, name, object_id=None):
    object_id = object_id or source_entry(root, commit, name)
    require(object_id is not None, 'GIT_SOURCE_UNAVAILABLE')
    size = git(root, 'cat-file', '-s', object_id)
    require(size.strip().isdigit() and int(size) <= LIMIT, 'SOURCE_BLOB_TOO_LARGE')
    return git(root, 'cat-file', 'blob', object_id)


def verify(receipt, root):
    require(type(receipt) is dict and receipt.get('schema_version') == 1 and
            type(receipt.get('schema_version')) is int, 'INVALID_SOURCE_RECEIPT')
    require(receipt.get('test_execution_during_reconciliation') is False and
            receipt.get('production_authorized') is False, 'INVALID_AUTHORITY_CLAIM')
    scopes = receipt.get('scopes')
    require(type(scopes) is list and 1 <= len(scopes) <= 8, 'SOURCE_SCOPES_REQUIRED')
    scope_ids = set()
    scope_commits = {}
    output = []
    work = 0
    for scope in scopes:
        require(type(scope) is dict, 'INVALID_SOURCE_SCOPE')
        identity, commit, files = (scope.get(k) for k in ('id', 'commit', 'files'))
        require(type(identity) is str and IDENTIFIER.fullmatch(identity) and identity not in scope_ids,
                'INVALID_SOURCE_SCOPE')
        scope_ids.add(identity)
        require(type(commit) is str and HEX40.fullmatch(commit), 'INVALID_SOURCE_COMMIT')
        require(git(root, 'cat-file', '-t', commit).strip() == b'commit', 'INVALID_SOURCE_COMMIT')
        scope_commits[identity] = commit
        require(type(files) is dict and 1 <= len(files) <= 512, 'SOURCE_FILES_REQUIRED')
        for name, expected in files.items():
            work += 1
            require(work <= 2048, 'SOURCE_COMPARISON_BUDGET_EXCEEDED')
            relative(name)
            require(type(expected) is str and HEX64.fullmatch(expected), 'INVALID_SOURCE_HASH')
            require(digest(blob(root, commit, name)) == expected, 'SOURCE_BLOB_MISMATCH')
        output.append({'scope': identity, 'commit': commit, 'verified_source_files': len(files)})
    authoritative = receipt.get('authoritative_scope')
    require(type(authoritative) is str and authoritative in scope_ids, 'AUTHORITATIVE_SCOPE_REQUIRED')
    history = receipt.get('historical_artifacts')
    require(type(history) is list and 1 <= len(history) <= 32, 'HISTORICAL_INVENTORY_REQUIRED')
    historical_output = []
    historical_paths = set()
    for item in history:
        require(type(item) is dict, 'INVALID_HISTORICAL_ARTIFACT')
        name = relative(item.get('path'))
        require(name not in historical_paths, 'DUPLICATE_HISTORICAL_ARTIFACT')
        historical_paths.add(name)
        expected, commit = item.get('raw_sha256'), item.get('preserved_in_commit')
        require(type(expected) is str and HEX64.fullmatch(expected) and
                type(commit) is str and HEX40.fullmatch(commit), 'INVALID_HISTORICAL_ARTIFACT')
        require(git(root, 'cat-file', '-t', commit).strip() == b'commit', 'INVALID_HISTORICAL_ARTIFACT')
        require(digest(blob(root, commit, name)) == expected, 'HISTORICAL_GIT_BYTES_CHANGED')
        try:
            with (root / name).open('rb') as source:
                current = source.read(LIMIT + 1)
        except OSError:
            raise Refused('HISTORICAL_FILE_MISSING') from None
        require(digest(current) == expected, 'HISTORICAL_WORKTREE_BYTES_CHANGED')
        require(item.get('classification') == 'historical_capture_not_current_checkout_manifest',
                'HISTORICAL_SCOPE_LABEL_REQUIRED')
        comparisons = []
        fields, against = item.get('source_fields', []), item.get('compare_to', [])
        require(type(fields) is list and len(fields) <= 3 and all(type(k) is str for k in fields),
                'INVALID_HISTORICAL_COMPARISON')
        require(type(against) is list and len(against) <= 8 and all(type(k) is str and k in scope_commits for k in against),
                'INVALID_HISTORICAL_COMPARISON')
        # Comparisons consume the same bounded bytes whose raw hash passed.
        # Reopening here would permit a different, unverified map to be used.
        document = parse_json(current) if fields else None
        for field in fields:
            require(type(document) is dict, 'INVALID_HISTORICAL_SOURCE_MAP')
            captured = document if field == '$' else document.get(field)
            require(type(captured) is dict and 1 <= len(captured) <= 512, 'INVALID_HISTORICAL_SOURCE_MAP')
            for scope_id in against:
                matched, missing, different = [], [], []
                for path, expected_hash in captured.items():
                    work += 1
                    require(work <= 2048, 'SOURCE_COMPARISON_BUDGET_EXCEEDED')
                    relative(path)
                    require(type(expected_hash) is str and HEX64.fullmatch(expected_hash), 'INVALID_SOURCE_HASH')
                    object_id = source_entry(root, scope_commits[scope_id], path)
                    if object_id is None:
                        missing.append(path)
                    else:
                        if digest(blob(root, scope_commits[scope_id], path, object_id)) == expected_hash:
                            matched.append(path)
                        else:
                            different.append(path)
                comparisons.append({'field': field, 'against_scope': scope_id,
                                    'matched_files': matched, 'absent_companion_files': missing,
                                    'different_files': different})
        historical_output.append({'path': name, 'raw_bytes_preserved': True, 'comparisons': comparisons})
    return {'status': 'VERIFIED_SOURCE_SCOPE_RECONCILIATION',
            'verification_scope': 'pinned_git_blobs_and_preserved_historical_bytes_only', 'scopes': output,
            'authoritative_scope': receipt['authoritative_scope'],
            'historical_artifacts': historical_output, 'tests_executed': False,
            'production_authorized': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, default=Path(__file__).with_name('SOURCE_EVIDENCE.json'))
    args = parser.parse_args(argv)
    try:
        root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
        result = verify(read_json(args.receipt), root)
    except (Refused, subprocess.SubprocessError, OSError) as error:
        reason = str(error) if isinstance(error, Refused) else 'SOURCE_RECONCILIATION_UNAVAILABLE'
        print(json.dumps({'status': 'REFUSED', 'reason': reason, 'tests_executed': False,
                          'production_authorized': False}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
