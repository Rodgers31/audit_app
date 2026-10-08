# Local backup acquisition ownership

Issue #499 was reproduced on a native Linux Docker daemon with a UID:GID
1000:1000 caller. At source commit `2b04f1518bbc04ed7b99d60373c29b1ef148d443`,
the acquisition client ran as root and created its bind-mounted partial archive
with mode 0600. The caller then received `PermissionError` reading that file.
Docker Desktop's host filesystem mapping had masked this failure on macOS.

`acquire_local` now runs its bounded client with the caller's effective UID:GID.
Before archive inspection and exclusive publication, the partial must be a
regular non-symlink file owned by that caller and group, with mode 0600 inside
the caller's mode-0700 temporary directory. The fix grants no public access.
Read-only or public output modes and foreign ownership refuse publication.
The existing archive, digest, internal-network, snapshot, wall/transport,
stderr, cleanup and restore checks remain in force.

The new actual lifecycle regression checks archive ownership/mode, readable
bytes, matching archive digest and private receipt reload. Its pre-fix native
Linux execution failed at the same archive open as the hosted runner. The fixed
native Linux cohort passed 55 tests and 157 subtests, without skips. The macOS
compatibility cohort, including logical restore verification, passed 79 tests.
A real root-owned mode-0600 control was refused by the nonroot Linux caller
without changing its owner or permissions.

The disposable native ARM Linux daemon used classic vfs storage and a private
Unix socket, with no host socket mount, published ports or network during
tests. Its Python was 3.14.8; macOS used 3.13.9. Hosted native amd64/Python
3.12.14 execution remains the final platform acceptance gate. The original
accepted restore and past receipts were untouched.

Caller review: the operator CLI and local rehearsal tests reach `acquire_local`
and receive this fix. `inspect_archive` and `restore_local` consume reviewed
private files and preserve their existing guards. `reviewed_pg_acquisition`
has a separate privileged supervisor and failure-evidence publication path;
its acquisition writer is unchanged by this local-client repair.
