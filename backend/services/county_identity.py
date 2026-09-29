"""Kenyan county numbering, distinct from historical app route identifiers.

Source: Constitution of Kenya, First Schedule (PDF pages 164–165):
https://www.parliament.go.ke/sites/default/files/2017-05/The_Constitution_of_Kenya_2010.pdf
Cross-checked all 47 against KNBS KIHBS categories on 2026-09-27.
"""
import re

OFFICIAL_COUNTY_CODES = {
    "001": "Mombasa",
    "002": "Kwale",
    "003": "Kilifi",
    "004": "Tana River",
    "005": "Lamu",
    "006": "Taita Taveta",
    "007": "Garissa",
    "008": "Wajir",
    "009": "Mandera",
    "010": "Marsabit",
    "011": "Isiolo",
    "012": "Meru",
    "013": "Tharaka Nithi",
    "014": "Embu",
    "015": "Kitui",
    "016": "Machakos",
    "017": "Makueni",
    "018": "Nyandarua",
    "019": "Nyeri",
    "020": "Kirinyaga",
    "021": "Murang'a",
    "022": "Kiambu",
    "023": "Turkana",
    "024": "West Pokot",
    "025": "Samburu",
    "026": "Trans Nzoia",
    "027": "Uasin Gishu",
    "028": "Elgeyo Marakwet",
    "029": "Nandi",
    "030": "Baringo",
    "031": "Laikipia",
    "032": "Nakuru",
    "033": "Narok",
    "034": "Kajiado",
    "035": "Kericho",
    "036": "Bomet",
    "037": "Kakamega",
    "038": "Vihiga",
    "039": "Bungoma",
    "040": "Busia",
    "041": "Siaya",
    "042": "Kisumu",
    "043": "Homa Bay",
    "044": "Migori",
    "045": "Kisii",
    "046": "Nyamira",
    "047": "Nairobi",
}


def _name_key(name):
    if not isinstance(name, str):
        return ""
    name = re.sub(r"\s+county$", "", name.strip(), flags=re.IGNORECASE)
    name = name.casefold().replace("’", "'")
    name = re.sub(r"[-/]", " ", name)
    name = " ".join(name.split())
    return "nairobi" if name == "nairobi city" else name


_NAME_TO_CODE = {_name_key(name): code for code, name in OFFICIAL_COUNTY_CODES.items()}


def official_county_code(name):
    """Exact known county identity only; never substring-match an institution."""
    return _NAME_TO_CODE.get(_name_key(name))


def legacy_county_route_id(name):
    """Keep pre-existing bookmarks on the same county; these are not codes."""
    code = official_county_code(name)
    return {"001": "047", "047": "001"}.get(code, code)


def resolve_official_county_entity(db, code):
    """Resolve an official code, never through the app's legacy URL mapping."""
    from models import Country, Entity, EntityType

    if code not in OFFICIAL_COUNTY_CODES:
        return None
    matches = [
        entity
        for entity in db.query(Entity)
        .join(Country, Entity.country_id == Country.id)
        .filter(Entity.type == EntityType.COUNTY, Country.iso_code == "KEN")
        .all()
        if official_county_code(entity.canonical_name) == code
    ]
    return matches[0] if len(matches) == 1 else None
