"""Retain actual phase outcomes, including non-strict XPASS absent from JUnit."""
import json
import os
from pathlib import Path

REPORTS = []


def pytest_runtest_logreport(report):
    REPORTS.append({'nodeid': report.nodeid, 'phase': report.when,
                    'outcome': report.outcome, 'wasxfail': getattr(report, 'wasxfail', None)})


def pytest_sessionfinish(session, exitstatus):
    path = Path(os.environ['NIGHTLY_PHASE_REPORT'])
    with path.open('x') as stream:
        json.dump({'exitstatus': int(exitstatus), 'reports': REPORTS}, stream, allow_nan=False)
