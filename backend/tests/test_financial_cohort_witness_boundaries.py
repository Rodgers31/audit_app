"""Reject malformed snapshot selectors before any SQL, including identifiers."""
from types import SimpleNamespace
import pytest
from seeding.financial_cohort_witness import input_fingerprints, FinancialCohortWitness, witness_is_intact
from seeding.source_observations import SourceObservationUnavailable


class NoSQL:
    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))
    def execute(self, *args, **kwargs):
        raise AssertionError('Invalid selector reached SQL')


@pytest.mark.parametrize('selector', [None, {}, {'loans; DROP TABLE loans': [1]},
    {'loans': []}, {'loans': [True]}, {'loans': [0]}, {'loans': [-1]},
    {'loans': [1.0]}, {'loans': ['1']}, {'loans': [2147483648]},
    {'loans': list(range(1, 4002))}])
def test_snapshot_selector_refuses_before_sql(selector):
    with pytest.raises(SourceObservationUnavailable):
        input_fingerprints(NoSQL(), selector, lock=True)


def test_snapshot_lock_mode_is_typed():
    with pytest.raises(SourceObservationUnavailable):
        input_fingerprints(NoSQL(), {'loans': [1]}, lock='true')


def test_witness_cannot_be_constructed_from_supplied_metadata():
    with pytest.raises(TypeError):
        FinancialCohortWitness({'record_id': 1})
    forged = object.__new__(FinancialCohortWitness)
    forged.value = {'record_id': 1}
    assert not forged.intact()


@pytest.mark.parametrize('subclass', [False, True])
def test_issuer_validation_ignores_object_supplied_verdicts(subclass):
    class Pretend(FinancialCohortWitness):
        def intact(self):
            return True
    forged = object.__new__(Pretend if subclass else FinancialCohortWitness)
    forged.value = {'record_id': 1}
    if not subclass:
        forged.intact = lambda: True
    assert forged.intact() is True
    assert witness_is_intact(forged) is False
