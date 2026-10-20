"""Fixture-only post-exec guard and raw lifecycle copy. Never in production."""
import os
import sys

try:
    import runpy
    boundary = runpy.run_path('/host/isolation.py')['post_exec']()
    # Keep every capability dropped; do not weaken a host sysctl for inert TLS.
    # Keep application import precedence; helper names avoid /app namespace packages.
    sys.path.append('/host')
    import portmap
    portmap.install()
    if sys.orig_argv == [sys.executable, '-B', '-c',
            'import endpoints; endpoints.main("127.0.0.4",prewarm=True)']:
        import endpoints
        original_server = endpoints.ThreadingHTTPServer
        endpoints.ThreadingHTTPServer = lambda address, handler: portmap.endpoint_server(
            address, handler, original_server)
    # Keep Render stdout direct: the final PID1 stop proof must not depend on
    # an observer which the kernel kills at the same instant as PID1 exits.
    class Tee:
        def __init__(self, original):
            self.original = original
            self.pending = ''
        def write(self, value):
            self.pending += value
            if len(self.pending) > 1024 * 1024:
                raise RuntimeError('Log line bound')
            while '\n' in self.pending:
                line, self.pending = self.pending.split('\n', 1)
                data = (line + '\n').encode()
                fd = os.open('/evidence/supervisor.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                try:
                    if os.write(fd, data) != len(data):
                        raise RuntimeError('Raw lifecycle copy incomplete')
                finally:
                    os.close(fd)
                self.original.write(line + '\n')
                self.original.flush()
            return len(value)
        def flush(self):
            self.original.flush()
        def __getattr__(self, name):
            return getattr(self.original, name)
    sys.stdout = Tee(sys.stdout)
    runpy.run_path('/harness/b27_sitecustomize.py')
    if 'social.worker' in sys.orig_argv:
        # Observe the existing receipt at its exact private pipe descriptor.
        # Export a consistent inert backup only after resources closed, before
        # native exits. The real launcher must still validate/reap the worker.
        sys.path.append('/host')
        from custody import receipt_descriptor
        receipt_fd = receipt_descriptor(sys.orig_argv)
        original_write = os.write
        exported = False
        def write(fd, content):
            global exported
            if fd == receipt_fd:
                if exported:
                    raise RuntimeError('Duplicate native receipt')
                exported = True
                sys.path.append('/host')
                from custody import closure_backup
                if closure_backup(content) is not True:
                    raise RuntimeError('Positive backup completion required')
            return original_write(fd, content)
        os.write = write
except BaseException as error:
    # Python normally prints and ignores sitecustomize exceptions. That would
    # run the worker after a failed boundary check, so refuse the entire exec.
    try:
        import json
        detail = str(error) if type(error) in (RuntimeError, ValueError) else type(error).__name__
        os.write(2, (json.dumps(dict(event='host_fixture_startup_refused',
            error_type=type(error).__name__, error_code=detail[:160])) + '\n').encode())
    finally:
        os._exit(78)
