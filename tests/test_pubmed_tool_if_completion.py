from __future__ import annotations

from pubmed_tool.app import FixturePubMedClient
from pubmed_tool.if_lookup import FixtureImpactFactorLookup, threshold_status
from pubmed_tool.models import PaperRecord
from pubmed_tool.search import SearchOrchestrator


KEYWORDS = ["cancer", "diabetes", "cell division", "분비단백질", "immune response"]


def _records() -> dict[str, dict]:
    return {
        "Journal of Cancer Systems": {
            "years": {"2025": 14.2, "2024": 13.8, "2023": 12.9, "2022": 12.1, "2021": 11.7},
            "source": "JCR licensed export",
            "trust": "official",
        },
        "Diabetes Public Metrics": {
            "years": {"2024": 9.1, "2023": 10.4, "2022": 11.2, "2021": 10.2},
            "source": "BioxBio candidate",
            "trust": "public_candidate",
        },
        "Cell Division Reports": {
            "years": {"2025": 10.1},
            "source": "JournalMetrics candidate",
            "trust": "public_candidate",
        },
        "Secretome Research": {
            "years": {"2025": 8.8, "2024": 12.4, "2023": 12.0, "2022": 11.6, "2021": 11.2},
            "source": "Research.com candidate",
            "trust": "public_candidate",
        },
        "Immune Response Journal": {
            "years": {"2025": 15.0, "2024": 14.0},
            "source": "JCR licensed export",
            "trust": "official",
        },
        "Low Impact Control": {
            "years": {"2025": 2.0, "2024": 2.2, "2023": 2.1},
            "source": "fixture",
            "trust": "public_candidate",
        },
    }


def _paper(keyword: str, journal: str, index: int) -> PaperRecord:
    return PaperRecord(
        pmid=f"{keyword}-{index}",
        title=f"{keyword} fixture paper",
        journal=journal,
        year="2025",
        abstract=f"{keyword} biology and clinical evidence",
    )


def test_five_keyword_fixture_searches_have_if_threshold_passing_rows():
    journal_by_keyword = {
        "cancer": "Journal of Cancer Systems",
        "diabetes": "Diabetes Public Metrics",
        "cell division": "Cell Division Reports",
        "분비단백질": "Secretome Research",
        "immune response": "Immune Response Journal",
    }
    lookup = FixtureImpactFactorLookup(records=_records())

    for index, keyword in enumerate(KEYWORDS):
        papers = [
            _paper(keyword, journal_by_keyword[keyword], index),
            _paper(keyword, "Low Impact Control", index),
        ]
        orchestrator = SearchOrchestrator(
            pubmed_client=FixturePubMedClient(papers),
            if_lookup=lookup,
            llm_summary_limit=0,
        )
        job = orchestrator.run_search(keyword, [], impact_factor_threshold=10, llm_enabled=False)
        passing = [row for row in job.results if row.if_threshold_status == "pass"]

        assert passing, keyword
        for row in passing:
            evidence = row.impact_factor
            assert evidence.latest_if is not None or evidence.five_year_avg_if is not None
            assert (evidence.latest_if or 0) >= 10 or (evidence.five_year_avg_if or 0) >= 10
            assert evidence.trust_label.value in {"official", "public_candidate"}


def test_latest_and_five_year_average_if_are_computed_from_latest_available_years():
    lookup = FixtureImpactFactorLookup(
        records={
            "Average Test Journal": {
                "years": {
                    "2025": 9.0,
                    "2024": 10.0,
                    "2023": 11.0,
                    "2022": 12.0,
                    "2021": 13.0,
                    "2020": 99.0,
                },
                "trust": "public_candidate",
                "source": "fixture",
            }
        }
    )

    evidence = lookup.lookup("Average Test Journal")

    assert evidence.latest_if == 9.0
    assert evidence.latest_if_year == 2025
    assert evidence.five_year_avg_if == 11.0
    assert evidence.five_year_avg_range == "2021-2025"
    assert evidence.five_year_avg_count == 5
    assert threshold_status(evidence, 10) == "pass"


def test_csv_annual_columns_and_impact_factor_year_columns_are_parsed(tmp_path):
    from pubmed_tool.if_lookup import FixtureImpactFactorLookup

    csv_path = tmp_path / "if_multi.csv"
    csv_path.write_text(
        "journal,2025,impact_factor_2024,if_2023,source,trust,status\n"
        "Annual IF Journal,15,14,13,JCR export,official,known\n",
        encoding="utf-8",
    )
    lookup = FixtureImpactFactorLookup(data_path=csv_path)

    evidence = lookup.lookup("Annual IF Journal")

    assert evidence.latest_if == 15.0
    assert evidence.latest_if_year == 2025
    assert evidence.five_year_avg_if == 14.0
    assert evidence.five_year_avg_range == "2023-2025"
    assert evidence.five_year_avg_count == 3
    assert evidence.trust_label.value == "official"


def test_public_snippet_rejects_citescore_sjr_and_h_index_metrics():
    from pubmed_tool.if_lookup import extract_google_if_candidate

    payload = {
        "items": [
            {
                "title": "Journal of Cancer Systems metrics",
                "snippet": "Journal of Cancer Systems CiteScore 2025 is 14.2 and h-index is 99.",
                "link": "https://example.test/metrics",
            },
            {
                "title": "Journal of Cancer Systems impact factor",
                "snippet": "Journal of Cancer Systems Journal Impact Factor 2024 is 11.4.",
                "link": "https://example.test/if",
            },
        ]
    }

    evidence = extract_google_if_candidate("Journal of Cancer Systems", payload)

    assert evidence.value == 11.4
    assert evidence.trust_label.value == "public_candidate"


def test_public_html_adapter_extracts_yearly_values_from_bioxbio_like_table():
    from pubmed_tool.if_lookup import extract_public_if_candidate

    html = """
    <html><body>
      <h1>Seminars in Perinatology Impact Factor IF 2025|2024|2023</h1>
      <table>
        <tr><th>Year</th><th>Impact Factor (IF)</th></tr>
        <tr><td>2025</td><td>3.2</td></tr>
        <tr><td>2024</td><td>3.2</td></tr>
        <tr><td>2023</td><td>2.8</td></tr>
      </table>
    </body></html>
    """

    evidence = extract_public_if_candidate("Seminars in Perinatology", html, provider="BioxBio", source_url="https://example.test/bioxbio")

    assert evidence.latest_if == 3.2
    assert evidence.latest_if_year == 2025
    assert evidence.five_year_avg_if == 3.067
    assert evidence.five_year_avg_range == "2023-2025"
    assert evidence.trust_label.value == "public_candidate"


def test_hybrid_lookup_merges_public_sources_and_caches(tmp_path):
    from pubmed_tool.if_lookup import HybridImpactFactorLookup, ImpactFactorEvidence, TrustLabel

    class _Adapter:
        def __init__(self, value: ImpactFactorEvidence) -> None:
            self.value = value
            self.calls = 0

        def lookup(self, _journal: str) -> ImpactFactorEvidence:
            self.calls += 1
            return self.value

    first = _Adapter(
        ImpactFactorEvidence(
            value=3.2,
            year=2025,
            source="JournalMetrics",
            source_url="https://example.test/jm",
            trust_label=TrustLabel.PUBLIC_CANDIDATE,
            retrieved_at="2026-04-19T00:00:00Z",
        )
    )
    second = _Adapter(
        ImpactFactorEvidence(
            value=2.8,
            year=2024,
            source="Research.com",
            source_url="https://example.test/research",
            trust_label=TrustLabel.PUBLIC_CANDIDATE,
            retrieved_at="2026-04-19T00:00:00Z",
        )
    )
    lookup = HybridImpactFactorLookup(cache_dir=tmp_path, adapters=[first, second])

    a = lookup.lookup("Seminars in Perinatology")
    b = lookup.lookup("Seminars in Perinatology")

    assert a.latest_if == 3.2
    assert a.five_year_avg_if == 3.0
    assert a.five_year_avg_range == "2024-2025"
    assert a.trust_label.value == "public_candidate"
    assert b.latest_if == 3.2
    assert first.calls == 1
    assert second.calls == 1


def test_journalmetrics_dataset_adapter_uses_public_json_index_and_pubmed_title_aliases(tmp_path):
    from pubmed_tool.if_lookup import JournalMetricsImpactFactorLookup

    class _Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class _Session:
        def __init__(self):
            self.calls = 0

        def get(self, _url, timeout):
            self.calls += 1
            return _Response(
                [
                    {
                        "journal": "Nature Nanotechnology",
                        "jcr": "NAT NANOTECHNOL",
                        "issn": "1748-3387",
                        "IF": "34.9",
                        "5yearIF": "40.4",
                    },
                    {
                        "journal": "SENSORS",
                        "jcr": "SENSORS-BASEL",
                        "issn": "1424-8220",
                        "IF": "3.4",
                        "5yearIF": "4.0",
                    },
                ]
            )

    session = _Session()
    lookup = JournalMetricsImpactFactorLookup(session=session, cache_dir=tmp_path)

    nature = lookup.lookup("Nature nanotechnology")
    sensors = lookup.lookup("Sensors (Basel, Switzerland)")

    assert nature.latest_if == 34.9
    assert nature.five_year_avg_if == 40.4
    assert nature.trust_label.value == "public_candidate"
    assert sensors.latest_if == 3.4
    assert session.calls == 1


def test_ui_if_threshold_filter_hides_unknown_rows():
    from pathlib import Path

    source = Path("pubmed_tool/static/app.js").read_text(encoding="utf-8")

    assert "(!hasImpactValue || (latestIf < activeFilters.minIf && avgIf < activeFilters.minIf))" in source


def test_compact_result_includes_if_source_evidence():
    lookup = FixtureImpactFactorLookup(records=_records())
    orchestrator = SearchOrchestrator(
        pubmed_client=FixturePubMedClient([_paper("cancer", "Journal of Cancer Systems", 1)]),
        if_lookup=lookup,
        llm_summary_limit=0,
    )

    row = orchestrator.run_search("cancer", [], impact_factor_threshold=10, llm_enabled=False).results[0].compact_dict()

    assert row["impact_factor"]["source"] == "JCR licensed export"
    assert row["impact_factor"]["sources"]


def test_public_seed_contains_common_high_if_journals_for_live_smoke_fallback():
    from pubmed_tool.if_lookup import FixtureImpactFactorLookup

    lookup = FixtureImpactFactorLookup()

    assert lookup.lookup("Cell").latest_if and lookup.lookup("Cell").latest_if >= 10
    assert lookup.lookup("Nature").latest_if and lookup.lookup("Nature").latest_if >= 10
    assert lookup.lookup("Circulation").latest_if and lookup.lookup("Circulation").latest_if >= 10
    assert lookup.lookup("European Heart Journal").latest_if and lookup.lookup("European Heart Journal").latest_if >= 10
    assert lookup.lookup("Nature structural & molecular biology").latest_if and lookup.lookup("Nature structural & molecular biology").latest_if >= 10
    assert lookup.lookup("Journal of thrombosis and haemostasis : JTH").latest_if and lookup.lookup("Journal of thrombosis and haemostasis : JTH").latest_if >= 10
    assert lookup.lookup("Blood").latest_if and lookup.lookup("Blood").latest_if >= 10
