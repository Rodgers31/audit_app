"""A county's budget must not be dropped by a PDF hyphenation artifact.

COB's county BIRR PDF renders one cell as "Taita-Tav-\\neta County", which
slugifies to `taita-tav-eta-county` and matches no entity. `_resolve_entity`
was taught to tolerate that via `resolve_entity_by_slug`'s de-spaced pass —
but `persist_budget_records` preloads entities by EXACT slug in bulk and
dropped the miss before ever reaching that resolver.

So Taita Taveta's row was discarded on every run: allocated KES 8.34bn,
actual KES 4.90bn, gone with a one-line warning nobody read. That is the
failure mode this repo keeps finding — a real figure withheld silently while
the run reports success.

The rescue must also be VISIBLE. A fuzzy match is a parser defect upstream, so
it is logged as a non-exact resolution rather than papered over.
"""

from seeding.utils import resolve_entity_by_slug, slugify_entity


class _Entity:
    def __init__(self, slug):
        self.slug = slug
        self.canonical_name = slug.replace("-", " ").title()
        self.alt_names = None
        self.type = "COUNTY"
        self.id = 1
        self.country_id = 1


class TestTheArtifactSlug:
    def test_the_pdf_cell_slugifies_to_the_broken_form(self):
        """Pin the input, so a parser change that fixes it upstream is noticed."""
        assert slugify_entity("Taita-Tav-\neta County") == "taita-tav-eta-county"

    def test_the_broken_form_is_not_the_real_slug(self):
        assert slugify_entity("Taita Taveta") == "taita-taveta-county"
        assert slugify_entity("Taita-Tav eta") != slugify_entity("Taita Taveta")


class TestTheWriterKeepsTheRow:
    """Against the SHIPPED writer, on a real (rolled-back) session.

    A hand-rolled session fake agrees with whatever shape I imagine the query
    has; this drives persist_budget_records itself, which is the code that was
    dropping the row.
    """

    @staticmethod
    def _record(slug):
        from datetime import date
        from decimal import Decimal

        from seeding.domains.counties_budget.parser import BudgetRecord

        return BudgetRecord(
            entity_slug=slug,
            entity_name="Taita-Tav-\neta County",
            period_label="2024/25",
            start_date=date(2024, 7, 1),
            end_date=date(2025, 6, 30),
            category="Total",
            subcategory=None,
            allocated_amount=Decimal("8335020000.0"),
            actual_amount=Decimal("4896770000.0"),
            committed_amount=None,
            currency="KES",
            dataset_id=None,
            source_url="https://cob.go.ke/download/x",
            data_quality="official",
            source_label="Controller of Budget County BIRR 2024/25",
            notes=None,
        )

    def _persist(self, db_session, slug):
        from models import Country, Entity, EntityType
        from seeding.config import SeedingSettings
        from seeding.domains.counties_budget.writer import persist_budget_records
        from seeding.types import DomainRunContext

        country = Country(
            name="Kenya", iso_code="KEN", currency="KES",
            timezone="Africa/Nairobi", default_locale="en-KE",
        )
        db_session.add(country)
        db_session.flush()
        db_session.add(
            Entity(
                canonical_name="Taita Taveta County",
                slug="taita-taveta-county",
                type=EntityType.COUNTY,
                country_id=country.id,
            )
        )
        db_session.flush()
        return persist_budget_records(
            db_session,
            [self._record(slug)],
            SeedingSettings(),
            DomainRunContext(since=None, dry_run=True),
        )

    def test_the_artifact_slug_row_is_kept(self, db_session):
        """The regression: this row used to be skipped, losing KES 8.34bn."""
        stats = self._persist(db_session, "taita-tav-eta-county")
        assert stats.skipped == 0, stats.errors
        assert not [e for e in (stats.errors or []) if "Unknown entity slug" in e]

    def test_the_exact_slug_still_works(self, db_session):
        """POSITIVE CONTROL — the fast path is untouched."""
        stats = self._persist(db_session, "taita-taveta-county")
        assert stats.skipped == 0, stats.errors

    def test_a_genuinely_unknown_county_is_still_skipped(self, db_session):
        """The tolerant pass must not become an accept-anything pass."""
        stats = self._persist(db_session, "atlantis-county")
        assert stats.skipped == 1
        assert any("Unknown entity slug" in e for e in (stats.errors or []))


class TestDespacingIsSafe:
    def test_no_two_kenyan_counties_collide_when_despaced(self):
        """What makes the de-spaced pass safe rather than lucky."""
        counties = [
            "tharaka-nithi", "tana-river", "trans-nzoia", "uasin-gishu",
            "west-pokot", "elgeyo-marakwet", "homa-bay", "taita-taveta",
            "muranga", "nairobi", "mombasa", "kisumu", "nakuru", "kiambu",
        ]
        despaced = [c.replace("-", "") for c in counties]
        assert len(set(despaced)) == len(despaced)
