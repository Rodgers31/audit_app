"""
Tests for county name normalization in the ETL normalizer.
Verifies all 47 Kenya counties resolve and tricky spelling variants are handled.
"""

import sys
import os

# Ensure the etl package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from etl.normalizer import DataNormalizer


@pytest.fixture()
def normalizer():
    return DataNormalizer()


# All 47 canonical county names (without " County" suffix)
ALL_47_COUNTIES = [
    "Mombasa",
    "Kwale",
    "Kilifi",
    "Tana River",
    "Lamu",
    "Taita-Taveta",
    "Garissa",
    "Wajir",
    "Mandera",
    "Marsabit",
    "Isiolo",
    "Meru",
    "Tharaka-Nithi",
    "Embu",
    "Kitui",
    "Machakos",
    "Makueni",
    "Nyandarua",
    "Nyeri",
    "Kirinyaga",
    "Murang'a",
    "Kiambu",
    "Turkana",
    "West Pokot",
    "Samburu",
    "Trans-Nzoia",
    "Uasin Gishu",
    "Elgeyo-Marakwet",
    "Nandi",
    "Baringo",
    "Laikipia",
    "Nakuru",
    "Narok",
    "Kajiado",
    "Kericho",
    "Bomet",
    "Kakamega",
    "Vihiga",
    "Bungoma",
    "Busia",
    "Siaya",
    "Kisumu",
    "Homa Bay",
    "Migori",
    "Kisii",
    "Nyamira",
    "Nairobi",
]


class TestAll47CountiesPresent:
    """Every canonical county name should normalize successfully."""

    @pytest.mark.parametrize("county_name", ALL_47_COUNTIES)
    def test_canonical_name_resolves(self, normalizer, county_name):
        result = normalizer.normalize_entity_name(county_name)
        assert result is not None, f"{county_name} did not resolve"
        assert result["canonical_name"] == f"{county_name} County" or result[
            "canonical_name"
        ].replace("\u2019", "'") == f"{county_name} County"
        assert result["confidence"] == 1.0

    def test_exactly_47_counties_in_mapping(self, normalizer):
        counties = normalizer.entity_mappings["counties"]
        # Count unique canonical names (variants share the same canonical)
        unique = {v["canonical_name"] for v in counties.values()}
        assert len(unique) == 47, f"Expected 47 unique counties, got {len(unique)}: {unique}"


class TestMurangaVariants:
    @pytest.mark.parametrize(
        "variant",
        ["Muranga", "Murang'a", "Murang\u2019a", "Murang'a County", "MURANGA", "muranga"],
    )
    def test_muranga_variants(self, normalizer, variant):
        result = normalizer.normalize_entity_name(variant)
        assert result is not None, f"'{variant}' did not resolve"
        assert result["canonical_name"] == "Murang'a County"


class TestTharakaNithiVariants:
    @pytest.mark.parametrize(
        "variant",
        ["Tharaka Nithi", "Tharaka-Nithi", "THARAKA NITHI", "Tharaka-Nithi County"],
    )
    def test_tharaka_nithi_variants(self, normalizer, variant):
        result = normalizer.normalize_entity_name(variant)
        assert result is not None, f"'{variant}' did not resolve"
        assert result["canonical_name"] == "Tharaka-Nithi County"


class TestElgeyoMarakwetVariants:
    @pytest.mark.parametrize(
        "variant",
        ["Elgeyo Marakwet", "Elgeyo-Marakwet", "ELGEYO MARAKWET", "Elgeyo-Marakwet County"],
    )
    def test_elgeyo_marakwet_variants(self, normalizer, variant):
        result = normalizer.normalize_entity_name(variant)
        assert result is not None, f"'{variant}' did not resolve"
        assert result["canonical_name"] == "Elgeyo-Marakwet County"


class TestTaitaTavetaVariants:
    @pytest.mark.parametrize(
        "variant",
        ["Taita Taveta", "Taita-Taveta", "TAITA TAVETA", "Taita-Taveta County"],
    )
    def test_taita_taveta_variants(self, normalizer, variant):
        result = normalizer.normalize_entity_name(variant)
        assert result is not None, f"'{variant}' did not resolve"
        assert result["canonical_name"] == "Taita-Taveta County"


class TestTransNzoiaVariants:
    @pytest.mark.parametrize(
        "variant",
        ["Trans Nzoia", "Trans-Nzoia", "TRANS NZOIA", "Trans-Nzoia County"],
    )
    def test_trans_nzoia_variants(self, normalizer, variant):
        result = normalizer.normalize_entity_name(variant)
        assert result is not None, f"'{variant}' did not resolve"
        assert result["canonical_name"] == "Trans-Nzoia County"


class TestHomaBayVariants:
    @pytest.mark.parametrize(
        "variant",
        ["Homa Bay", "HomaBay", "HOMA BAY", "Homabay", "Homa Bay County"],
    )
    def test_homa_bay_variants(self, normalizer, variant):
        result = normalizer.normalize_entity_name(variant)
        assert result is not None, f"'{variant}' did not resolve"
        assert result["canonical_name"] == "Homa Bay County"


class TestCaseInsensitive:
    def test_uppercase(self, normalizer):
        result = normalizer.normalize_entity_name("NAIROBI")
        assert result is not None
        assert result["canonical_name"] == "Nairobi County"

    def test_mixed_case(self, normalizer):
        result = normalizer.normalize_entity_name("nAiRoBi")
        assert result is not None
        assert result["canonical_name"] == "Nairobi County"

    def test_with_county_suffix(self, normalizer):
        result = normalizer.normalize_entity_name("Nakuru County")
        assert result is not None
        assert result["canonical_name"] == "Nakuru County"
