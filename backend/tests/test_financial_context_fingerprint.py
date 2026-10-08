"""Reviewed financial context must mean the same thing on Python 3.12/3.13."""

from copy import deepcopy

import pytest

from tests import test_apis_no_invented_national_figures as figures


SOURCE = "def observed_budget():\n    budget = 1234\n    return budget\n"
# Exact existing Python 3.13 dump format, with empty structural lists omitted.
# Fixed receipt, not derived from whichever interpreter executes this test.
REVIEWED_SHA = "0947868cabc7e59eb779ae1e516d9eba1296f581185d9db445404da9d25cbd96"


def entry():
    return {
        "ast_sha256": REVIEWED_SHA,
        "sites": [{
            "signature": figures.find_invented_figures(SOURCE)[0].split(": ", 1)[1],
            "reason": "Owned unresolved figure control; source remains detectable",
            "disposition": "unresolved typed finance",
            "tracking": "https://github.com/Rodgers31/audit_app/issues/301",
        }],
    }


def test_same_reviewed_context_keeps_its_existing_pin():
    figures._assert_reviewed_figure_source(SOURCE, "owned.py", entry())
    figures._assert_reviewed_figure_source(
        SOURCE.replace("budget = 1234", "budget = 1234  # formatting only"),
        "owned.py", entry(),
    )
    assert figures.find_invented_figures(SOURCE), "raw detector must still bite"


@pytest.mark.parametrize("changed", [
    SOURCE.replace("1234", "1235"),
    SOURCE.replace("budget = 1234", "budget = measured"),
    SOURCE.replace("return budget", "publish(budget)\n    return budget"),
    SOURCE.replace("return budget", "return None"),
    SOURCE.replace("return budget", "return []"),
    SOURCE.replace("return budget", "return {}"),
    SOURCE.replace("return budget", "return [None]"),
    SOURCE.replace("observed_budget()", "observed_budget(*args, **kwargs)"),
    SOURCE.replace("observed_budget()", "observed_budget(flag=None)"),
    SOURCE + "publish(observed_budget())\n",
    SOURCE + "debt = 5678\n",
    SOURCE.replace("budget = 1234", "budget = 1234  # figure-literal-ok: changed suppression"),
    "",
])
def test_numeric_context_null_and_empty_structure_mutations_still_refuse(changed):
    with pytest.raises(AssertionError):
        figures._assert_reviewed_figure_source(changed, "owned.py", entry())


@pytest.mark.parametrize("key", ["reason", "disposition", "tracking"])
def test_review_dispositions_cannot_be_removed(key):
    broken = deepcopy(entry())
    broken["sites"][0][key] = ""
    with pytest.raises(AssertionError):
        figures._assert_reviewed_figure_source(SOURCE, "owned.py", broken)
