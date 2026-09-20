"""The COB county BIRR PDF must not be re-parsed when nothing has changed.

WHAT WAS WRONG
--------------
``get_or_download_pdf`` already stopped the nightly re-downloading the 48MB
county BIRR report. Nothing stopped it re-PARSING it:

    Sep 16 (run 35048000013)  Parsed COB county BIRR PDF (188 records, 251.5s)
    Sep 17 (run 35174426953)  Parsed COB county BIRR PDF (188 records, 249.1s)
    Sep 18 (run 35299414702)  Parsed COB county BIRR PDF (188 records, 258.5s)

Same document (``49758224`` bytes, same cache filename), same 1,048 tables
extracted, same 188 records, ~250s of a 1320s global budget — 19% — every
night. Runs 35174426953 and 35299414702 then ran out of budget and dropped
domains.

WHAT THESE TESTS PIN
--------------------
1. Two fetches of an unchanged document parse it ONCE.
   *Seen to fail against the pre-fix fetcher: ``extract_all_tables`` is
   called twice.*
2. A document whose bytes change is re-parsed. A cache that cannot notice a
   new report is worse than no cache, because the site would go on publishing
   last quarter's figures under this quarter's headline.
3. A change to the PARSER is re-parsed, even though the document did not
   change. This is the failure mode a naive content-hash cache has: a fix
   lands, the tests pass, and production serves the pre-fix numbers until the
   publisher happens to republish.
4. ``Decimal`` money values survive the round trip as ``Decimal``, with the
   same value. JSON has no decimal type and ``float`` would quietly change
   published figures.
5. An empty parse is never banked, so one bad night cannot become permanent.
6. An unreadable entry re-parses instead of raising or serving nothing.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from seeding.config import SeedingSettings
from seeding.domains.counties_budget import fetcher as cb_fetcher
from seeding.parse_cache import content_digest, parse_with_cache, parser_digest
from seeding.pdf_parsers import CoBQuarterlyReportParser, ExtractedTable

#: The real document, for scale. Not fetched here — the tests run against a
#: stand-in file, because what is being tested is the CACHE KEY, not pdfplumber.
REAL_BIRR_BYTES = 49_758_224


@pytest.fixture()
def settings(tmp_path) -> SeedingSettings:
    s = SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs" / "seed.log",
        retry_backoff=0.01,
        max_retries=1,
        http_cache_enabled=False,
        live_pdf_fetch_enabled=True,
    )
    s.ensure_directories()
    (Path(s.cache_path) / "pdfs").mkdir(parents=True, exist_ok=True)
    return s


@pytest.fixture()
def fake_pdf(settings) -> Path:
    """A stand-in for the cached PDF, named so the parser reads FY2023/24.

    Lives in the same ``cache/pdfs`` directory the real one does, because the
    parse entry is stored beside it on purpose — CI restores that directory
    as a unit, so the document and its parse cannot come back separately.
    """
    path = Path(settings.cache_path) / "pdfs" / "Q2-2023-24-county-birr.pdf"
    path.write_bytes(b"%PDF-1.7\n" + b"county birr vintage A\n" * 64 + b"%%EOF\n")
    return path


def _tables():
    return [
        ExtractedTable(
            page_number=55,
            table_index=0,
            headers=["County", "Allocated", "Absorbed", "Rate"],
            rows=[
                ["Nairobi", "KES 44,621", "KES 30,102", "67.5%"],
                ["Mombasa", "KES 5,000", "KES 4,500", "90%"],
            ],
            bbox=(0, 0, 100, 100),
        )
    ]


class TestTheFetcherDoesNotReparseAnUnchangedDocument:
    """The end-to-end claim, exercised through the real fetcher function."""

    def _fetch(self, settings, pdf_path):
        with patch.object(cb_fetcher, "SeedingHttpClient", create=True):
            with patch(
                "seeding.pdf_download.get_or_download_pdf", return_value=pdf_path
            ):
                return cb_fetcher._download_and_parse_county_pdf(
                    client=None,
                    pdf_url="https://cob.go.ke/download/county-birr/?wpdmdl=16378",
                    settings=settings,
                )

    def test_two_runs_over_the_same_pdf_parse_it_once(self, settings, fake_pdf):
        """RED before the fix: extract_all_tables is called twice.

        ``extract_all_tables`` is the expensive step — the ~700-page,
        1,048-table pdfplumber walk that the run logs time at ~250s — so
        counting its calls counts the thing the nightly is paying for.
        """
        with patch(
            "seeding.pdf_parsers.extract_all_tables", side_effect=lambda p: _tables()
        ) as walk:
            first = self._fetch(settings, fake_pdf)
            second = self._fetch(settings, fake_pdf)

        assert walk.call_count == 1, (
            "the unchanged county BIRR PDF was walked "
            f"{walk.call_count} times; at the ~250s/walk the nightly logs "
            "that is the 19% of the budget this change exists to remove"
        )
        assert first == second, "the cached second run must be the same records"
        assert first, "the fixture tables should yield records at all"

    def test_a_changed_document_is_parsed_again(self, settings, fake_pdf):
        """COB republishing must reach the site, cache or no cache."""
        with patch(
            "seeding.pdf_parsers.extract_all_tables", side_effect=lambda p: _tables()
        ) as walk:
            self._fetch(settings, fake_pdf)
            before = content_digest(fake_pdf)
            fake_pdf.write_bytes(
                b"%PDF-1.7\n" + b"county birr vintage B\n" * 64 + b"%%EOF\n"
            )
            after = content_digest(fake_pdf)
            self._fetch(settings, fake_pdf)

        assert before != after, "the digest must move when the document does"
        assert walk.call_count == 2, (
            "a republished report was served from the cached parse of the "
            "previous one — the site would publish last quarter's figures"
        )

    def test_the_cache_is_disabled_by_settings(self, settings, fake_pdf):
        settings.parse_cache_enabled = False
        with patch(
            "seeding.pdf_parsers.extract_all_tables", side_effect=lambda p: _tables()
        ) as walk:
            self._fetch(settings, fake_pdf)
            self._fetch(settings, fake_pdf)
        assert walk.call_count == 2


class TestTheKeyTracksTheParserToo:
    """A content-only key would serve a fix's pre-fix output forever."""

    def test_the_parser_digest_is_the_parser_module(self):
        parser = CoBQuarterlyReportParser(Path("x.pdf"))
        expected = content_digest(
            Path(__import__("seeding.pdf_parsers", fromlist=["x"]).__file__)
        )
        assert parser_digest(parser.parse) == expected

    def test_an_edited_parser_misses_an_unchanged_document(
        self, settings, fake_pdf, tmp_path
    ):
        """Simulated by moving the parser digest, which is what an edit does.

        The digest is read from the parser's source FILE, so any edit to
        ``pdf_parsers.py`` — to ``parse`` or to any of the table-ranking,
        stitching and header-flattening helpers it leans on — moves it.
        """
        calls = {"n": 0}

        def parse_fn():
            calls["n"] += 1
            return [{"county": "Nairobi", "allocated": Decimal("1")}]

        cache_dir = Path(settings.cache_path) / "pdfs"
        with patch("seeding.parse_cache.parser_digest", return_value="parser-v1"):
            parse_with_cache(
                fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=parse_fn
            )
            parse_with_cache(
                fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=parse_fn
            )
        assert calls["n"] == 1, "same parser, same document — one parse"

        with patch("seeding.parse_cache.parser_digest", return_value="parser-v2"):
            parse_with_cache(
                fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=parse_fn
            )
        assert calls["n"] == 2, (
            "an edited parser reused the old parse: the fix would look landed "
            "while production kept serving the pre-fix numbers"
        )

    def test_an_unversionable_parser_is_not_cached_at_all(
        self, settings, fake_pdf
    ):
        """A sentinel string would be a STABLE key, which is the bug again.

        Two parsers whose source cannot be resolved would share one entry,
        and the second would be served the first's output — the exact
        failure the parser digest exists to prevent, reintroduced through
        its own error path. ``None`` means "do not cache this".
        """
        import functools

        assert parser_digest(object()) is None
        assert parser_digest(functools.partial(lambda: [])) is None

        def v1():
            return [{"county": "Nairobi", "allocated": Decimal("1")}]

        def v2():
            return [{"county": "Nairobi", "allocated": Decimal("2")}]

        cache_dir = Path(settings.cache_path) / "pdfs"
        with patch("seeding.parse_cache.parser_digest", return_value=None):
            first = parse_with_cache(
                fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=v1
            )
            second = parse_with_cache(
                fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=v2
            )
        assert first != second, (
            "an unversionable parser was cached, and a different parser was "
            "then served its output"
        )
        assert not list(cache_dir.glob("k.*.parse.json")), (
            "an entry was written for a parser that cannot be versioned"
        )

    def test_a_pdfplumber_upgrade_misses(self, settings, fake_pdf):
        """The extraction library is not in our source, and it is what
        actually reads the tables. An upgrade must not be served the old
        library's output out of the cache."""
        calls = {"n": 0}

        def parse_fn():
            calls["n"] += 1
            return [{"county": "Nairobi"}]

        cache_dir = Path(settings.cache_path) / "pdfs"
        for extra in ("pdfplumber=0.11.4", "pdfplumber=0.11.4", "pdfplumber=0.12.0"):
            parse_with_cache(
                fake_pdf,
                cache_dir=cache_dir,
                kind="k",
                parse_fn=parse_fn,
                key_extra=extra,
            )
        assert calls["n"] == 2, (
            "a pdfplumber upgrade reused the parse produced by the previous "
            "version"
        )

    def test_the_fetcher_puts_the_whole_pdf_stack_in_the_key(
        self, settings, fake_pdf
    ):
        """Pin the CALL SITE, not just the capability. A key_extra nobody
        passes is a guard that does nothing.

        pdfminer.six as well as pdfplumber: extract_tables() clusters what
        pdfminer produced, and requirements.txt pins neither (pdfplumber has
        a floor, pdfminer.six is unpinned), so an upgrade can arrive on any
        rebuild of the runner image.
        """
        from importlib.metadata import version

        seen = {}

        real = cb_fetcher.__dict__.get("parse_with_cache")
        assert real is None, "parse_with_cache is imported inside the function"

        def spy(*args, **kwargs):
            seen.update(kwargs)
            return [{"county": "Nairobi", "fiscal_year": "2023/24"}]

        with patch("seeding.parse_cache.parse_with_cache", spy):
            with patch(
                "seeding.pdf_download.get_or_download_pdf", return_value=fake_pdf
            ):
                cb_fetcher._download_and_parse_county_pdf(
                    client=None,
                    pdf_url="https://cob.go.ke/download/x/?wpdmdl=1",
                    settings=settings,
                )
        key_extra = seen.get("key_extra", "")
        for package in ("pdfplumber", "pdfminer.six"):
            assert f"{package}={version(package)}" in key_extra, (
                f"the fetcher left {package} out of the cache key: {seen}"
            )


class TestTheRoundTripIsExact:
    def test_decimals_come_back_as_decimals(self, settings, fake_pdf):
        records = [
            {
                "county": "Nairobi",
                "allocated": Decimal("44621.00"),
                "absorbed": Decimal("30102.55"),
                "absorption_rate": 67.5,
                "subcategory": None,
                "notes": ["a", {"nested": Decimal("0.1")}],
            }
        ]
        cache_dir = Path(settings.cache_path) / "pdfs"
        first = parse_with_cache(
            fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=lambda: records
        )
        second = parse_with_cache(
            fake_pdf,
            cache_dir=cache_dir,
            kind="k",
            parse_fn=lambda: pytest.fail("should have been a cache hit"),
        )
        assert second == first == records
        assert isinstance(second[0]["allocated"], Decimal)
        assert second[0]["allocated"] == Decimal("44621.00")
        assert isinstance(second[0]["notes"][1]["nested"], Decimal)


class TestAMissIsObservableAndSafe:
    def test_an_empty_parse_is_not_banked(self, settings, fake_pdf):
        calls = {"n": 0}

        def parse_fn():
            calls["n"] += 1
            return []

        cache_dir = Path(settings.cache_path) / "pdfs"
        parse_with_cache(fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=parse_fn)
        parse_with_cache(fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=parse_fn)
        assert calls["n"] == 2, (
            "an empty parse was cached — one bad night would freeze the "
            "domain on the fixture for the life of the CI cache"
        )

    def test_a_corrupt_entry_reparses_rather_than_raising(self, settings, fake_pdf):
        cache_dir = Path(settings.cache_path) / "pdfs"
        parse_with_cache(
            fake_pdf,
            cache_dir=cache_dir,
            kind="k",
            parse_fn=lambda: [{"county": "Nairobi"}],
        )
        entry = next(cache_dir.glob("k.*.parse.json"))
        entry.write_text("{not json", encoding="utf-8")

        records = parse_with_cache(
            fake_pdf,
            cache_dir=cache_dir,
            kind="k",
            parse_fn=lambda: [{"county": "Mombasa"}],
        )
        assert records == [{"county": "Mombasa"}]

    def test_hit_and_miss_are_distinguishable_in_the_log(
        self, settings, fake_pdf, caplog
    ):
        """'The cache is working' and 'the cache is quietly wrong' must not
        read the same in a nightly log."""
        cache_dir = Path(settings.cache_path) / "pdfs"
        with caplog.at_level("INFO", logger="seeding.parse_cache"):
            parse_with_cache(
                fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=lambda: [{"a": 1}]
            )
            miss_log = caplog.text
            caplog.clear()
            parse_with_cache(
                fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=lambda: [{"a": 1}]
            )
            hit_log = caplog.text

        assert "parse cache MISS" in miss_log
        assert "parse cache HIT" in hit_log
        assert "parse cache MISS" not in hit_log

    def test_an_entry_for_a_different_document_is_rejected(
        self, settings, fake_pdf
    ):
        """The filename is not evidence. The BODY has to agree.

        Copying one entry over another's path is how a bad merge of two
        cache snapshots, or a hand rescue, goes wrong — and a HIT skips
        ``_check_county_coverage``, so a wrong entry publishes a county
        total the parser itself would have refused.
        """
        cache_dir = Path(settings.cache_path) / "pdfs"
        other = cache_dir / "Q1-2023-24-other.pdf"
        other.write_bytes(b"%PDF-1.7\nanother document\n%%EOF\n")

        parse_with_cache(
            fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=lambda: [{"q": 1}]
        )
        parse_with_cache(
            other, cache_dir=cache_dir, kind="k", parse_fn=lambda: [{"q": 2}]
        )
        a, b = sorted(cache_dir.glob("k.*.parse.json"))
        b.write_bytes(a.read_bytes())  # the wrong body under the right name

        calls = {"n": 0}

        def reparse():
            calls["n"] += 1
            return [{"q": 99}]

        for pdf in (fake_pdf, other):
            parse_with_cache(pdf, cache_dir=cache_dir, kind="k", parse_fn=reparse)
        assert calls["n"] >= 1, (
            "an entry whose recorded content digest names a different "
            "document was served"
        )

    def test_a_short_entry_is_rejected_rather_than_served(
        self, settings, fake_pdf
    ):
        """``record_count`` was written and never read, so an entry could
        lose rows and still be served — and the caller would report a
        partial county table as a whole one."""
        cache_dir = Path(settings.cache_path) / "pdfs"
        parse_with_cache(
            fake_pdf,
            cache_dir=cache_dir,
            kind="k",
            parse_fn=lambda: [{"c": 1}, {"c": 2}, {"c": 3}],
        )
        entry = next(cache_dir.glob("k.*.parse.json"))
        body = json.loads(entry.read_text(encoding="utf-8"))
        body["records"] = body["records"][:1]  # drop rows, leave the count
        entry.write_text(json.dumps(body), encoding="utf-8")

        records = parse_with_cache(
            fake_pdf,
            cache_dir=cache_dir,
            kind="k",
            parse_fn=lambda: [{"c": 1}, {"c": 2}, {"c": 3}],
        )
        assert len(records) == 3, "a short entry was served as though whole"

    def test_records_that_are_not_objects_are_rejected(self, settings, fake_pdf):
        """The caller does ``record.get(...)`` on every element."""
        cache_dir = Path(settings.cache_path) / "pdfs"
        parse_with_cache(
            fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=lambda: [{"c": 1}]
        )
        entry = next(cache_dir.glob("k.*.parse.json"))
        body = json.loads(entry.read_text(encoding="utf-8"))
        body["records"] = ["Nairobi"]
        entry.write_text(json.dumps(body), encoding="utf-8")

        records = parse_with_cache(
            fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=lambda: [{"c": 1}]
        )
        assert records == [{"c": 1}]

    def test_records_that_do_not_round_trip_are_never_cached(
        self, settings, fake_pdf
    ):
        """JSON has no tuple and no non-string dict key, and a field shaped
        like the Decimal tag would come back a Decimal. Rather than assert
        that today's records avoid all three, check it — so a future field
        that does not survive is reparsed, never silently altered."""
        cache_dir = Path(settings.cache_path) / "pdfs"
        for records in (
            [{"county": "Nairobi", "bbox": (0, 0, 612, 792)}],
            [{"county": "Nairobi", "by_quarter": {1: "Q1"}}],
            [{"county": "Nairobi", "raw_cell": {"__decimal__": "4"}}],
        ):
            calls = {"n": 0}

            def parse_fn(r=records):
                calls["n"] += 1
                return r

            first = parse_with_cache(
                fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=parse_fn
            )
            second = parse_with_cache(
                fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=parse_fn
            )
            assert first == second == records, (
                f"{records!r} was altered by the cache round trip"
            )
            assert calls["n"] == 2, (
                f"{records!r} does not round-trip but was cached anyway"
            )

    def test_the_real_cob_record_shape_does_round_trip(self, settings, fake_pdf):
        """Positive control for the check above: the shape the CoB parser
        actually emits must still be cached, or the guard has disabled the
        feature it was meant to protect."""
        cache_dir = Path(settings.cache_path) / "pdfs"
        real_shape = [
            {
                "county": "Baringo",
                "category": "Total",
                "subcategory": None,
                "allocated": Decimal("9542.03"),
                "absorbed": Decimal("4092.38"),
                "absorption_rate": 43.0,
                "currency": "KES",
                "quarter": "Q1",
                "fiscal_year": "2024/25",
            }
        ]
        calls = {"n": 0}

        def parse_fn():
            calls["n"] += 1
            return real_shape

        parse_with_cache(
            fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=parse_fn
        )
        second = parse_with_cache(
            fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=parse_fn
        )
        assert calls["n"] == 1, "the real record shape was refused by the guard"
        assert second == real_shape
        assert isinstance(second[0]["allocated"], Decimal)

    def test_a_read_only_cache_dir_with_a_bad_entry_does_not_raise(
        self, settings, fake_pdf
    ):
        """A cache problem must not turn a parse the caller could still
        perform into a domain failure. The rejected-entry unlink used to sit
        outside the try."""
        import os
        import stat

        cache_dir = Path(settings.cache_path) / "pdfs"
        parse_with_cache(
            fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=lambda: [{"c": 1}]
        )
        entry = next(cache_dir.glob("k.*.parse.json"))
        entry.write_text("{not json", encoding="utf-8")
        mode = cache_dir.stat().st_mode
        os.chmod(cache_dir, stat.S_IRUSR | stat.S_IXUSR)
        try:
            records = parse_with_cache(
                fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=lambda: [{"c": 2}]
            )
        finally:
            os.chmod(cache_dir, mode)
        assert records == [{"c": 2}]

    def test_the_entry_records_both_halves_of_the_key(self, settings, fake_pdf):
        """So an operator can check by hand which half moved."""
        cache_dir = Path(settings.cache_path) / "pdfs"
        parse_with_cache(
            fake_pdf, cache_dir=cache_dir, kind="k", parse_fn=lambda: [{"a": 1}]
        )
        entry = next(cache_dir.glob("k.*.parse.json"))
        meta = json.loads(entry.read_text(encoding="utf-8"))
        assert meta["content_sha256"] == content_digest(fake_pdf)
        assert meta["parser_sha256"]
        assert meta["record_count"] == 1
