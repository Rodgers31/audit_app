"""A county auditee belongs to the county row we already hold.

The consolidated county volumes number their TOC 1..47, and the Blue Book
loader read those as national vote numbers. It slugified "County Executive of
Kilifi" to `county-executive-of-kilifi`, missed the real `kilifi-county`, and
created an Entity of type MINISTRY with `vote: 3`:

    Created entity County Executive of Kilifi (ministry, vote 3)
    Created entity County Executive of Taita/Taveta (ministry, vote 6)

A completed run would have written ~94 mis-typed entities duplicating counties
that already exist. Only the 600s timeout rolling the run back prevented it,
which is luck rather than design.

Verified against both real volumes: 94 of 94 entries resolve to existing
COUNTY entities and nothing is created.
"""

import pytest

from seeding.domains.audits.loader import CountyEntityUnresolved, _county_entity


@pytest.fixture()
def counties(db_session):
    from models import Country, Entity, EntityType

    country = Country(
        name="Kenya", iso_code="KEN", currency="KES",
        timezone="Africa/Nairobi", default_locale="en-KE",
    )
    db_session.add(country)
    db_session.flush()
    for name in ("Kilifi", "Taita Taveta", "Nairobi", "Homa Bay"):
        db_session.add(
            Entity(
                country_id=country.id,
                type=EntityType.COUNTY,
                canonical_name=f"{name} County",
                slug=f"{name.lower().replace(' ', '-')}-county",
            )
        )
    db_session.flush()
    return db_session


class TestCountyEntriesResolve:
    @pytest.mark.parametrize(
        "entry,expect",
        [
            ("County Executive of Kilifi", "kilifi-county"),
            ("County Assembly of Kilifi", "kilifi-county"),
            ("County Government of Kilifi", "kilifi-county"),
        ],
    )
    def test_all_three_auditee_forms_map_to_one_county(self, counties, entry, expect):
        """Executive and assembly are two auditees of the SAME county."""
        e = _county_entity(counties, entry)
        assert e is not None and e.slug == expect

    def test_a_slashed_name_resolves(self, counties):
        """The TOC prints "Taita/Taveta"."""
        e = _county_entity(counties, "County Executive of Taita/Taveta")
        assert e is not None and e.slug == "taita-taveta-county"

    def test_nairobi_city_resolves_to_nairobi(self, counties):
        """The TOC says "Nairobi City"; the county row is "Nairobi"."""
        e = _county_entity(counties, "County Assembly of Nairobi City")
        assert e is not None and e.slug == "nairobi-county"

    def test_it_returns_a_county_type_not_a_ministry(self, counties):
        from models import EntityType

        e = _county_entity(counties, "County Executive of Kilifi")
        assert e.type == EntityType.COUNTY

    def test_nothing_is_created(self, counties):
        from models import Entity

        before = counties.query(Entity).count()
        _county_entity(counties, "County Executive of Kilifi")
        counties.flush()
        assert counties.query(Entity).count() == before


class TestNonCountyEntriesAreLeftAlone:
    @pytest.mark.parametrize(
        "entry",
        ["State Department for Basic Education",
         "The National Treasury",
         "Ethics and Anti-Corruption Commission"],
    )
    def test_a_national_vote_is_not_treated_as_a_county(self, counties, entry):
        """None means "not a county entry" — the national path is unchanged."""
        assert _county_entity(counties, entry) is None


class TestUnresolvedCountiesAreRefused:
    def test_an_unknown_county_raises_rather_than_inventing_one(self, counties):
        """A public audit finding filed against a county we made up is worse
        than one absent."""
        with pytest.raises(CountyEntityUnresolved):
            _county_entity(counties, "County Executive of Atlantis")

    def test_the_error_names_what_failed(self, counties):
        with pytest.raises(CountyEntityUnresolved, match="Atlantis"):
            _county_entity(counties, "County Assembly of Atlantis")


class TestEnsureEntityIsTheOneThatWasBroken:
    """_ensure_entity is what created the ministries — test THAT.

    The tests above call _county_entity directly, so removing its call from
    _ensure_entity left all twelve of them green. Only this class goes red,
    which is the whole point: the bug was in the wiring, not the helper.
    """

    def test_a_county_entry_returns_the_existing_county(self, counties):
        from models import Entity, EntityType
        from seeding.domains.audits.loader import _ensure_entity

        country_id = counties.query(Entity).first().country_id
        before = counties.query(Entity).count()

        e = _ensure_entity(counties, country_id, "County Executive of Kilifi", 3)
        counties.flush()

        assert e.type == EntityType.COUNTY, "was created as a MINISTRY"
        assert e.slug == "kilifi-county"
        assert counties.query(Entity).count() == before, "created a duplicate"

    def test_a_national_vote_still_creates_its_mda(self, counties):
        """POSITIVE CONTROL — the national path must keep working."""
        from models import Entity, EntityType
        from seeding.domains.audits.loader import _ensure_entity

        country_id = counties.query(Entity).first().country_id
        e = _ensure_entity(
            counties, country_id, "State Department for Basic Education", 1011
        )
        counties.flush()
        assert e.type == EntityType.MINISTRY

    def test_a_commission_vote_still_types_as_commission(self, counties):
        from models import Entity, EntityType
        from seeding.domains.audits.loader import _ensure_entity

        country_id = counties.query(Entity).first().country_id
        e = _ensure_entity(counties, country_id, "Some Commission", 2011)
        counties.flush()
        assert e.type == EntityType.COMMISSION
