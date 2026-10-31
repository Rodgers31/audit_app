import sys

def _false_helper():
    assert 26 == 27, 'deliberately false helper assertion in collected test module'

def test_false_test_assertion():
    assert 26 == 27, 'deliberately false test assertion'

def test_false_helper_assertion():
    _false_helper()

def test_real_optimized_runtime():
    if sys.flags.optimize != 1:
        raise RuntimeError('This calibration must execute in a true -O interpreter')
