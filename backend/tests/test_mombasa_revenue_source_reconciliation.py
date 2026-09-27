"""Pinned report arithmetic; source labels remain separate from our inference."""
import json
from decimal import Decimal
from pathlib import Path


def test_mombasa_summary_matches_accrual_components_not_cash():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/mombasa_revenue_basis.json").read_text()
    )
    chapter, summary = fixture["chapter"], fixture["summary"]
    ordinary, fif = chapter["ordinary_osr"], chapter["fif"]
    for row in (ordinary, fif):
        assert Decimal(row["cash"]) + Decimal(row["receivables"]) == Decimal(
            row["accrual"]
        )
    cash = sum(Decimal(row["cash"]) for row in (ordinary, fif))
    accrual = sum(Decimal(row["accrual"]) for row in (ordinary, fif))
    assert cash == Decimal("6214590483")
    assert accrual == Decimal("21126223896")
    assert accrual - cash == Decimal(chapter["total_receivables"])
    rounded_components = sum(
        (Decimal(row["accrual"]) / 1_000_000).quantize(Decimal("0.01"))
        for row in (ordinary, fif)
    )
    assert rounded_components == Decimal(summary["total_osr_million"])
    assert rounded_components == Decimal(summary["ordinary_osr_million"]) + Decimal(
        summary["fif_aia_million"]
    )
    assert rounded_components * 1_000_000 - accrual == Decimal("6104")
    assert Decimal(chapter["total_cash_including_opening_balance"]) + Decimal(
        chapter["total_receivables"]
    ) == Decimal(chapter["total_accrual_including_opening_balance"])
