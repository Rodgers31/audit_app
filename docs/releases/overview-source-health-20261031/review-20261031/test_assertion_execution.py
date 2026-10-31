import sys
import pytest

def denied():
    assert False, "DELIBERATE_HELPER_FALSE_ASSERT"

def test_interpreter_is_optimized():
    if sys.flags.optimize != 1:
        pytest.fail("Expected actual optimized interpreter")

def test_rewritten_false_assert_fails():
    assert False, "DELIBERATE_TEST_FALSE_ASSERT"

def test_rewritten_helper_false_assert_fails():
    denied()
