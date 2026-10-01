"""Reasoned comments attach to one AST site, never an adjacent expression."""
import ast
import io
import tokenize


def suppressed(
    lines: list[str], node: ast.AST, marker: str, sites: list[ast.AST]
) -> bool:
    comments = [
        t
        for t in tokenize.generate_tokens(io.StringIO("\n".join(lines)).readline)
        if t.type == tokenize.COMMENT
        and marker in t.string
        and t.string.split(marker, 1)[1].strip()
    ]
    for comment in comments:
        line, col = comment.start
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
