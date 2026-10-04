"""Exact source comments can be reused; AST ownership must remain live."""
import ast
from unittest.mock import patch

import pytest

from tests import _guard_suppression as guard

MARKER = "figure-literal-ok:"


def values(source):
    return [node.value for node in ast.parse(source).body if isinstance(node, ast.Assign)]


def decisions(source, marker=MARKER, sites=None):
    sites = values(source) if sites is None else sites
    return [guard.suppressed(source.splitlines(), node, marker, sites) for node in sites]


def test_repeated_source_sites_tokenize_once_without_changing_their_decisions():
    source = "budget = 12345 # figure-literal-ok: reviewed receipt\nrevenue = 23456\n"
    sites = values(source)
    with patch.object(guard.tokenize, "generate_tokens", wraps=guard.tokenize.generate_tokens) as tokenize:
        for _ in range(3):
            assert decisions(source, sites=sites) == [True, False]
        assert tokenize.call_count == 1


@pytest.mark.parametrize("reason", ["", " ", "\t"])
def test_changed_reason_cannot_reuse_a_previous_approval(reason):
    supported = "budget = 7531 # figure-literal-ok: documented source\n"
    assert decisions(supported) == [True]
    changed = supported.replace("documented source", reason)
    assert decisions(changed) == [False]
    assert decisions(supported) == [True]


def test_marker_and_changed_source_are_part_of_the_comment_identity():
    source = "budget = 8642 # figure-literal-ok: documented source\n"
    assert decisions(source) == [True]
    assert decisions(source, "endpoint-literal-ok:") == [False]
    assert decisions(source.replace("#", "# unrelated: ").replace(MARKER, "unrelated:")) == [False]
    assert decisions(source) == [True]


def test_ast_site_ownership_is_recomputed_even_when_comment_bytes_match():
    source = "budget = 9753; revenue = 8642 # figure-literal-ok: documented source\n"
    budget, revenue = values(source)
    assert decisions(source, sites=[budget, revenue]) == [False, True]
    # With only the first site in the current query, it is the closest completed
    # owner. Comment caching must not reuse the other AST's suppressed verdict.
    assert decisions(source, sites=[budget]) == [True]
    assert decisions(source, sites=values(source)) == [False, True]


def test_comment_facts_are_immutable_and_cache_is_bounded():
    assert guard._reasoned_comment_positions.cache_parameters()["maxsize"] == 8
    source = "budget = 6420 # figure-literal-ok: documented source\n"
    positions = guard._reasoned_comment_positions(source, MARKER)
    assert isinstance(positions, frozenset)
    with pytest.raises(AttributeError):
        positions.add((1, 0))
    assert decisions(source) == [True]
    for index in range(12):
        guard._reasoned_comment_positions(f"# figure-literal-ok: source {index}\n", MARKER)
    assert guard._reasoned_comment_positions.cache_info().currsize <= 8
    assert decisions(source) == [True]
