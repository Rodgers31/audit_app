"""Reasoned comments attach to one AST site, never an adjacent expression."""
import ast
from functools import lru_cache
import io
import tokenize


@lru_cache(maxsize=8)
def _reasoned_comment_positions(source: str, marker: str) -> frozenset[tuple[int, int]]:
    """Reuse immutable lexical facts for these exact bytes and marker only."""
    return frozenset(
        t.start
        for t in tokenize.generate_tokens(io.StringIO(source).readline)
        if t.type == tokenize.COMMENT
        and marker in t.string
        and t.string.split(marker, 1)[1].strip()
    )


def suppressed(
    lines: list[str], node: ast.AST, marker: str, sites: list[ast.AST]
) -> bool:
    comments = _reasoned_comment_positions("\n".join(lines), marker)
    for line, col in comments:
        if lines[line - 1][:col].strip():
            # Inline: the closest completed site owns the comment.
            candidates = [
                s for s in sites if s.end_lineno == line and s.end_col_offset <= col
            ]
            if not candidates:
                continue
            last = max(s.end_col_offset for s in candidates)
            owners = [s for s in candidates if s.end_col_offset == last]
        else:
            # Standalone: the first site starting on the very next line.
            candidates = [s for s in sites if s.lineno == line + 1]
            if not candidates:
                continue
            first = min(s.col_offset for s in candidates)
            owners = [s for s in candidates if s.col_offset == first]
        if node in owners:
            return True
    return False
