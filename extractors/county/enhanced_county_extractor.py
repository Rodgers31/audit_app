"""
Enhanced County Data Extractor
Probes the Open County portals and Bajeti Yetu and reports what responded.

WITHDRAWN 2026-09-07 (issue #198): the generator that made up every county
figure this module emitted, and the four things computed from it.

    generate_mock_comprehensive_county_data  205-306  a population, budget,
                                                      revenue, debt, pending
                                                      bills, missing funds,
                                                      audit rating and list of
                                                      "major issues" for all 47
                                                      counties
    calculate_financial_health_score         309-326  graded a county out of
                                                      100 from those figures
    generate_county_rankings                 328-358  ordered all 47 by them,
                                                      including a
                                                      "worst_pending_bills"
                                                      table
    analytics_summary (in the run method)             totalled them, and
                                                      averaged the grade

It worked in two tiers and both were invented.

TIER 1 (210-260) hand-typed four counties. Nairobi City, Mombasa, Kiambu and
Nakuru each got a budget, a revenue, a debt, a pending-bills figure, a
``missing_funds`` amount (KSh 2.1 Bn for Nairobi City, 890 M for Mombasa), an
``audit_rating`` no auditor issued, and a ``major_issues`` list naming specific
failings. Counties are named public bodies; an unsourced allegation of missing
public money against one is a statement of fact about it, which is the issue
#182/#183 concern in the same form as the OAG withdrawal beside this one.

TIER 2 (267-285) derived the remaining counties from ``hash(county)``::

    pop_factor = hash(county) % 1000000 + 200000      # a POPULATION
    "audit_rating": ["A-", "B+", "B", "B-", "C+"][hash(county) % 5]

``hash()`` on a ``str`` is salted per process, so nothing it returns describes
the world and a rerun returns different figures. Five fresh interpreters put
Turkana's population at 600,436 / 1,015,787 / 1,056,980 / 508,167 / 860,893,
moving its budget, debt, pending bills and missing funds with it and changing
its audit rating four times. Kenya has counted these populations: the KNBS 2019
census sits in ``official_county_budget_extractor.py:45+``, and against it the
run above had Nairobi at 225,569 (-94.9%), Garissa at 231,825 (-72.4%) and Lamu
at 1,119,980 (+678.2%).

Tier 2 covered FORTY-FOUR counties, not the 43 the issue expected: the tier-1
table is keyed "Nairobi City" while the roster said "Nairobi", so the capital
never matched its own profile and fell through to ``hash()``.

NOT REPAIRABLE BY SUPPLYING THE CENSUS. Only ``population`` had a real source.
Every other field was a fixed multiple of it — budget = population x 3000,
revenue = 75% of budget, debt 25%, pending bills 15%, missing funds 5% — so
feeding the true census in would have produced better-looking invented budgets,
and 44 counties would still have shared a budget execution rate of exactly
75.0%, a debt-to-budget ratio of exactly 25.0% and a per-capita budget of
exactly 3000, the input constant echoed back. An audit rating and a
missing-funds allegation have no formula at all. A figure nobody measured is
withheld here, not replaced by a zero or by a tidier estimate.

WHY IT MATTERED WHILE NOTHING IMPORTED IT. ``main()`` writes
``enhanced_county_data.json`` into the working directory, and
``backend/bootstrap.py:75`` reads that filename out of ``BOOTSTRAP_DATA_DIR``
(default ``backend/data/reference/``). Running this module from that directory
would have overwritten a fixture that carries real KNBS populations, official
county codes and a ``"data_source": "realistic_estimate",
"needs_verification": true`` marker on every record — which is what
``bootstrap.py:290-300``'s modelled-field rule is written against — with an
unlabelled file of hash-derived populations. What this withdrawal closes is the
fabrication: there are no invented figures left to write. The FILENAME
collision is not closed and is called out at ``main()``; ``oag_audit_extractor``
has the same one.

The stored data was already cleared by ``backend/county_metrics_purge.py`` and
migration ``ce6ed007f696``, guarded by
``backend/tests/test_stored_county_metrics_are_cleared.py``, and none of that
is touched here. This is a regeneration hazard closed, not a live defect
fixed — nothing imported this module and no reader was reaching it.

What survives probes real endpoints and records what answered:
``discover_opencounty_apis``, ``extract_nairobi_opencounty_data`` and
``extract_bajeti_yetu_data``. They report nothing when they find nothing, which
is the correct answer when nothing was found.
``run_enhanced_county_extraction`` keeps those three steps and lost the two
generated ones. The 47-name ``self.counties`` roster went with the generator,
which was its only reader.

Two smaller claims in the surviving code went with them, both written whether
or not anything answered: ``extraction_summary.structured_sources_found``, a
literal ``2``, and the Nairobi record's ``"data_quality": "high"``. The record
now lists the endpoints that answered instead, and the run summary counts the
counties whose portal answered separately from the records written — the old
``counties_processed`` was ``len(self.county_data)``, which is 1 even when
every request failed.
"""

import json
import logging
from datetime import datetime

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedCountyDataExtractor:
    """Enhanced extractor for comprehensive county data from structured sources."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        self.county_data = {}
        self.api_endpoints = {}

    def discover_opencounty_apis(self):
        """Discover Open County API endpoints."""
        logger.info("🔍 Discovering Open County API endpoints...")

        try:
            # Check Open County main site
            response = self.session.get("https://opencounty.org", timeout=30)
            if response.status_code == 200:
                logger.info("✅ Open County site accessible")

                # Try common API patterns
                api_patterns = [
                    "https://opencounty.org/api/counties",
                    "https://opencounty.org/api/budgets",
                    "https://opencounty.org/api/indicators",
                    "https://opencounty.org/api/data/counties",
                    "https://api.opencounty.org/counties",
                    "https://data.opencounty.org/api/counties",
                ]

                for pattern in api_patterns:
                    try:
                        api_response = self.session.get(pattern, timeout=15)
                        if api_response.status_code == 200:
                            try:
                                data = api_response.json()
                                self.api_endpoints["counties"] = pattern
                                logger.info(f"✅ Found API endpoint: {pattern}")
                                break
                            except:
                                pass
                    except:
                        pass

        except Exception as e:
            logger.warning(f"⚠️ Open County discovery failed: {str(e)}")

    def extract_nairobi_opencounty_data(self):
        """Extract data from Nairobi's specific Open County portal."""
        logger.info("🏛️ Extracting Nairobi Open County data...")

        try:
            # Try Nairobi's specific API
            nairobi_apis = [
                "https://nairobi.opencounty.org/api/projects/filters",
                "https://nairobi.opencounty.org/api/budgets",
                "https://nairobi.opencounty.org/api/indicators/1",
            ]

            nairobi_data = {
                "county": "Nairobi City",
                "source": "Nairobi Open County Portal",
                # Which of the endpoints above actually answered. Recorded
                # rather than asserted: this used to carry
                # ``"data_quality": "high"``, written even when every request
                # failed and all three sections below stayed empty.
                "endpoints_answered": [],
                "projects": [],
                "indicators": {},
                "budget_summary": {},
            }

            for api_url in nairobi_apis:
                try:
                    response = self.session.get(api_url, timeout=20)
                    if response.status_code == 200:
                        data = response.json()

                        if "projects" in api_url:
                            nairobi_data["projects"] = data
                        elif "indicators" in api_url:
                            nairobi_data["indicators"] = data
                        elif "budgets" in api_url:
                            nairobi_data["budget_summary"] = data

                        nairobi_data["endpoints_answered"].append(api_url)
                        logger.info(f"✅ Nairobi data from: {api_url}")

                except Exception as e:
                    logger.warning(f"⚠️ Nairobi API {api_url} failed: {str(e)}")

            self.county_data["Nairobi"] = nairobi_data

        except Exception as e:
            logger.warning(f"⚠️ Nairobi Open County extraction failed: {str(e)}")

    def extract_bajeti_yetu_data(self):
        """Extract structured data from Bajeti Yetu portal."""
        logger.info("💰 Extracting Bajeti Yetu structured data...")

        try:
            # Try Bajeti Yetu portal
            bajeti_urls = [
                "https://bajetiyetu.treasury.go.ke",
                "https://bajetiyetu.treasury.go.ke/api/counties",
                "https://bajetiyetu.treasury.go.ke/data/budgets",
            ]

            for url in bajeti_urls:
                try:
                    response = self.session.get(url, timeout=30)
                    if response.status_code == 200:
                        logger.info(f"✅ Bajeti Yetu accessible: {url}")

                        # Check if it's JSON data
                        try:
                            data = response.json()
                            logger.info(f"✅ Found JSON data at: {url}")
                            # Process the structured data
                            if isinstance(data, list) and len(data) > 0:
                                for item in data[:5]:  # Sample first 5 items
                                    if "county" in str(item).lower():
                                        logger.info(
                                            f"📊 County data sample: {str(item)[:200]}..."
                                        )
                        except:
                            # Not JSON, but site is accessible
                            logger.info(f"✅ Bajeti Yetu site accessible (HTML)")

                except Exception as e:
                    logger.warning(f"⚠️ Bajeti Yetu {url} failed: {str(e)}")

        except Exception as e:
            logger.warning(f"⚠️ Bajeti Yetu extraction failed: {str(e)}")

    def run_enhanced_county_extraction(self):
        """Probe the county data sources and report what answered.

        Steps 4 and 5 of this method used to be "generate comprehensive county
        data" and "generate rankings"; they went with the methods behind them,
        and so did ``analytics_summary``, every field of which totalled or
        averaged figures the generator had made up. See the module docstring.
        """
        logger.info("\n" + "=" * 80)
        logger.info("🚀 ENHANCED COUNTY SOURCE DISCOVERY")
        logger.info("=" * 80)

        start_time = datetime.now()

        # Step 1: Discover structured data sources
        self.discover_opencounty_apis()

        # Step 2: Extract from Open County portals
        self.extract_nairobi_opencounty_data()

        # Step 3: Extract from Bajeti Yetu
        self.extract_bajeti_yetu_data()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Counties for which a portal actually answered. Counted from the
        # records rather than from len(self.county_data), because a record is
        # written whether or not anything responded — counting the records
        # would report 1 for a run in which every request failed. Not a
        # coverage claim either: how many counties these sources cover is
        # whatever they served, and this number cannot see it.
        answered = sum(
            1
            for record in self.county_data.values()
            if record.get("endpoints_answered")
        )

        # Compile results
        results = {
            "extraction_summary": {
                "counties_with_a_portal_that_answered": answered,
                "county_records_written": len(self.county_data),
                "api_endpoints_discovered": len(self.api_endpoints),
                "extraction_duration": duration,
                "timestamp": datetime.now().isoformat(),
            },
            "county_data": self.county_data,
            "data_sources": {
                "open_county_apis": self.api_endpoints,
                "nairobi_portal": "nairobi.opencounty.org",
                "bajeti_yetu": "bajetiyetu.treasury.go.ke",
                "fallback_sources": ["OCOB spreadsheets", "County PDFs"],
            },
        }

        # Log summary
        logger.info("\n📋 COUNTY SOURCE DISCOVERY COMPLETE:")
        logger.info(f"   🏛️ Counties whose portal answered: {answered}")
        logger.info(f"   📄 County records written: {len(self.county_data)}")
        logger.info(f"   🔗 API endpoints discovered: {len(self.api_endpoints)}")
        logger.info(f"   ⏱️ Duration: {duration:.1f} seconds")

        return results


def main():
    """Main function to run enhanced county source discovery.

    NOTE the output filename. ``backend/bootstrap.py:75`` reads
    ``enhanced_county_data.json`` out of ``BOOTSTRAP_DATA_DIR`` (default
    ``backend/data/reference/``), and that tracked fixture is NOT this module's
    output — it carries real KNBS populations, official county codes and a
    ``needs_verification`` marker on every record, from a later correction
    pass. Run this from that directory and you overwrite it with a probe
    report. The same collision exists in ``oag_audit_extractor.py``; renaming
    either is the owner's call, not this withdrawal's.
    """
    extractor = EnhancedCountyDataExtractor()
    results = extractor.run_enhanced_county_extraction()

    # Save results
    with open("enhanced_county_data.json", "w") as f:
        json.dump(results, f, indent=2)

    summary = results["extraction_summary"]
    print("\n✅ Enhanced county source discovery completed!")
    print(
        f"🏛️ Counties whose portal answered: {summary['counties_with_a_portal_that_answered']}"
    )
    print(f"🔗 API endpoints discovered: {summary['api_endpoints_discovered']}")
    print("📁 Results saved to: enhanced_county_data.json")


if __name__ == "__main__":
    main()
