# Financial guard context fingerprints on Python 3.12 and 3.13

The reviewed financial literal inventory pins complete parsed module context.
Its six module hashes and eighteen reviewed site dispositions remain unchanged.
Passing this guard still means no unreviewed drift; it does not certify an
unresolved figure as sourced.

Python 3.13 changed `ast.dump` to omit empty structural lists by default.
Python 3.12 includes them. The same source therefore produced different context
hashes in the CI Python 3.12 runner and the local Python 3.13 environment.
See the [official AST documentation](https://docs.python.org/3.13/library/ast.html#ast.dump)
and [CPython 3.13.9 implementation](https://github.com/python/cpython/blob/v3.13.9/Lib/ast.py).

`_context_ast_dump` explicitly renders the existing Python 3.13 pin format for
parsed source on both interpreters. It preserves node types, field ordering,
scalar values, nonempty children, literal `None`, and empty list/dict expression
nodes. It omits empty structural fields, optional absent fields and source
locations. Formatting and ordinary comments remain irrelevant to context;
the independent raw detector still checks changed suppressions.

No reviewed inventory was regenerated and no detector exemption was added.
The whole-module financial guard and fixed-hash regression run on both actual
interpreters. Mutations cover numeric changes, removed/new sites, callers,
function arguments, `None`, empty expression structures and suppression
changes. Missing reasons, tracking issues and dispositions remain refusals.

This establishes portability for the tested Python 3.12/3.13 grammar and
existing reviewed contexts. Future AST grammar changes require explicit review;
changing an inventory hash to silence a mismatch remains prohibited.
