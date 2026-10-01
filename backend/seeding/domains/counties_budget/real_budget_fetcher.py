"""Withdrawn population-formula county budget generator (#407).

The old script wrote estimated sector allocations into the registered domain's
budgets.json fixture. These amounts are archival estimates, never reported
whole budgets. Use counties_budget/fetcher.py for source-backed ingestion.
This compatibility module refuses all entry points before touching the disk.
"""


_WITHDRAWAL = (
    "RealBudgetDataFetcher is withdrawn: population-formula estimates cannot "
    "generate or overwrite county budget fixtures. Use the source-backed "
    "counties_budget domain instead."
)


class RealBudgetDataFetcher:
    """Compatibility name for the withdrawn generator; no generation is allowed."""

    def __init__(self, output_dir: str = None):
        raise RuntimeError(_WITHDRAWAL)

    def fetch_county_budget_allocations(self):
        # Refuse here too: unbound calls and __new__ bypass __init__.
        raise RuntimeError(_WITHDRAWAL)


if __name__ == "__main__":
    raise SystemExit(_WITHDRAWAL)
