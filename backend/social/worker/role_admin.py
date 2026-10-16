"""Explicit operator entrypoint. Never loads dotenv or creates a credential."""
import os
import re

from .config import WorkerConfig, create_worker_engine
from .arguments import PrivateArgumentParser
from .role_contract import install_worker_role, verify_worker_role


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__)
    parser.add_argument('--database-url-env', required=True, help='Name of the DSN variable; never the DSN value')
    parser.add_argument('--role', required=True)
    parser.add_argument('--schema', default='public')
    parser.add_argument('--native-platforms', action='store_true', help='Include the reviewed optional Threads/X/TikTok worker table contract')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--install', action='store_true', help='Grant the reviewed contract to an existing dedicated login')
    mode.add_argument('--verify', action='store_true', help='Verify through the actual worker login')
    args = parser.parse_args(argv)
    engine = None
    result = 0
    try:
        if re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', args.database_url_env) is None:
            raise ValueError()
        config = WorkerConfig(os.environ.get(args.database_url_env), database_schema=args.schema)
        engine = create_worker_engine(config)
        function = install_worker_role if args.install else verify_worker_role
        if args.native_platforms:
            function(engine, args.role, args.schema, platforms=True)
        else:
            function(engine, args.role, args.schema)
    except Exception:
        result = 1
    except KeyboardInterrupt:
        # An interrupt traceback would carry SQL and driver text; keep it fixed.
        result = 130
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except KeyboardInterrupt:
                result = 130
            except Exception:
                if result != 130:
                    result = 1
    # Only fixed output; no role, DSN, SQL, driver exception or connection rows.
    status = 'interrupted' if result == 130 else 'unavailable' if result else 'ok'
    print('{"event":"worker_role_' + ('installed' if args.install else 'verified') + '","status":"' + status + '"}')
    return result


if __name__ == '__main__':
    raise SystemExit(main())
