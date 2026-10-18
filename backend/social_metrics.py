"""One explicit native metrics command, never a polling/background service."""
import argparse
import json
from pathlib import Path
from uuid import UUID

from social.service import SocialError
from social.studio.native_metrics import CollectionCommand, configured_runtime


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target_id', type=UUID)
    parser.add_argument('--authorization', required=True, type=Path,
                        help='JSON CollectionCommand with exact credential generations, payload/remote/runtime hashes; no tokens')
    parser.add_argument('--enable-native-collection', action='store_true')
    args = parser.parse_args(argv)
    try:
        if not args.enable_native_collection:
            raise ValueError('Explicit collection switch required')
        runtime = configured_runtime()
        if not runtime.enabled:
            raise ValueError('Native collection disabled')
        with args.authorization.open('rb') as source:
            raw = source.read(4097)
        if len(raw) > 4096:
            raise ValueError('Authorization exceeds bound')
        command = CollectionCommand.model_validate_json(raw)
        # Importing application DB settings happens only after explicit local guards.
        from database import SessionLocal
        from social.studio.analytics import collect
        collection_id = collect(SessionLocal, args.target_id, runtime, enabled=True, authorization=command)
        from social.studio.models import MetricCollection
        with SessionLocal() as db:
            row = db.get(MetricCollection, collection_id)
            if row is None or row.state not in {'collected', 'unavailable'}:
                raise ValueError('Durable collection outcome unavailable')
            state = row.state
    except Exception:
        # No traceback/provider/configuration material reaches operator logs.
        print('Native metrics collection refused or failed; inspect stored collection history. No automatic retry.')
        return 1
    print(json.dumps({'collection_id': str(collection_id), 'state': state}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
