"""The retired web population route refuses every payload before fetching.

This replaces the old scraper/floor tests: no homepage, cached fixture or
structured-document payload may reach a population writer in the web process.
The dedicated World Bank/census tests supply the valid sourced controls.
"""
import asyncio
import importlib
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.mark.parametrize(
    "payload",
    [
        {"fetch_success": True, "national_population": 82, "census_year": 2026},
        {"fetch_success": True, "national_population": 47564296},
        {"fetch_success": True, "national_population": 57532493, "census_year": 2025},
        {
            "fetch_success": True,
            "counties": [{"county": "Mandera", "total_population": 1200890}],
            "census_year": 2019,
        },
    ],
)
def test_retired_web_population_writer_never_fetches(monkeypatch, payload):
    module = importlib.import_module("services.auto_seeder")
    seeder = module.AutoSeeder()
    fetch = AsyncMock(return_value=payload)
    monkeypatch.setattr(
        seeder.aggregator, "fetch_all_population_data", fetch, raising=False
    )
    database = Mock(side_effect=AssertionError("web population accessed database"))
    monkeypatch.setattr(module, "SessionLocal", database)
    with pytest.raises(ValueError, match="dedicated"):
        asyncio.run(seeder._seed_population_live())
    fetch.assert_not_called()
    database.assert_not_called()
