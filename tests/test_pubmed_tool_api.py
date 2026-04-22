from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pubmed_tool.app import FixturePubMedClient, create_app
from pubmed_tool.config import PubMedToolSettings
from pubmed_tool.models import PaperRecord
from pubmed_tool.search import SearchOrchestrator
from pubmed_tool.models import PaperRecord
from pubmed_tool.search import SearchOrchestrator


def _client() -> TestClient:
    papers = [
        PaperRecord(
            pmid="1001",
            title="Protein folding biomarkers for early sepsis",
            authors=["A Researcher"],
            journal="Journal of Fixture Medicine",
            year="2025",
            doi="10.1000/fixture.1",
            abstract="Protein and polypeptide folding biomarkers identify early sepsis risk.",
            links={"publisher": "https://publisher.example/paper/1001"},
        ),
        PaperRecord(
            pmid="1002",
            title="Cardiology workflow report",
            authors=["B Researcher"],
            journal="Unverified Biology Letters",
            year="2024",
            abstract="Cardiology operational workflow without the target protein concept.",
        ),
    ]
    orchestrator = SearchOrchestrator(pubmed_client=FixturePubMedClient(papers))
    return TestClient(create_app(orchestrator=orchestrator))


def test_fixture_backed_api_flow_preserves_evidence_and_detail_contracts():
    client = _client()

    expansions_response = client.post("/api/pubmed/expansions", json={"question": "protein folding sepsis"})
    assert expansions_response.status_code == 200
    expansions = expansions_response.json()["expansions"]
    assert any(item["term"] == "protein" and item["synonym"] == "polypeptide" for item in expansions)

    search_response = client.post(
        "/api/pubmed/search",
        json={
            "question": "protein folding sepsis",
            "expansions": expansions,
            "impact_factor_threshold": 10,
            "max_results": 50,
        },
    )
    assert search_response.status_code == 200
    payload = search_response.json()
    rows = payload["results"]
    assert payload["result_count"] == 2
    assert rows[0]["pmid"] == "1001"
    assert rows[0]["text_evidence_basis"] == "abstract_only"
    assert rows[0]["evidence_label"] == "Abstract 기반 평가입니다. 원문 결론은 확인하지 않았습니다."
    assert rows[0]["impact_factor"]["trust_label"] == "official"

    detail_response = client.get(f"/api/pubmed/results/{payload['job_id']}/papers/1001")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["abstract"]
    assert detail["keywords"]
    assert detail["access_status"] == "publisher_link"
    assert detail["download_permission"] == "user_upload_required"
    assert detail["links"]["publisher"] == "https://publisher.example/paper/1001"


def test_authenticated_pdf_policy_check_rejects_remote_session_material():
    client = _client()

    response = client.post(
        "/api/pubmed/results/job/papers/pmid/authenticated-pdf-policy-check",
        json={"url": "https://publisher.example/auth.pdf", "cookie": "session=abc"},
    )

    assert response.status_code == 400
    assert "remote authenticated PDF references are not accepted" in response.text


def test_static_ui_normalizes_backend_trust_label_shape():
    source = Path("pubmed_tool/static/app.js").read_text(encoding="utf-8")

    assert "impact.trust_label || impact.trust" in source


def test_static_ui_direct_search_continues_after_expansion_generation():
    source = Path("pubmed_tool/static/app.js").read_text(encoding="utf-8")

    assert "english_query: state.englishQuery || question" in source
    assert "Review synonym suggestions, then run the search again." not in source
    assert "state.expansions = fixture.expansions.map(normalizeExpansion);\n    renderExpansions();\n  }\n\n  setLoading(true" not in source
    assert "fixture.expansions.map(normalizeExpansion)" not in source


def test_configured_impact_factor_csv_surfaces_official_scores(tmp_path):
    csv_path = tmp_path / "if.csv"
    csv_path.write_text(
        "journal,impact_factor,year,source,source_url,trust,status\n"
        "Archives of biochemistry and biophysics,12.4,2024,JCR licensed export,https://example.test/jcr,official,known\n",
        encoding="utf-8",
    )
    settings = PubMedToolSettings(impact_factor_data_path=csv_path)
    app = create_app(
        settings=settings,
        orchestrator=SearchOrchestrator(
            pubmed_client=FixturePubMedClient(
                [
                    PaperRecord(
                        pmid="if-1",
                        title="Metal site occupancy",
                        journal="Archives of biochemistry and biophysics",
                        year="2024",
                        abstract="metal sensor protein",
                    )
                ]
            )
        ),
    )
    # create_app respects an injected orchestrator, so explicitly apply the configured lookup for this fixture.
    from pubmed_tool.if_lookup import FixtureImpactFactorLookup

    app.state.orchestrator.if_lookup = FixtureImpactFactorLookup(data_path=csv_path)
    client = TestClient(app)
    response = client.post(
        "/api/pubmed/search",
        json={"question": "metal protein", "expansions": [], "impact_factor_threshold": 10, "max_results": 50},
    )

    row = response.json()["results"][0]
    assert row["impact_factor"]["value"] == 12.4
    assert row["impact_factor"]["trust_label"] == "official"
    assert row["if_threshold_status"] == "pass"


def test_google_custom_search_snippet_can_supply_public_if_candidate(tmp_path):
    from pubmed_tool.if_lookup import GoogleCustomSearchImpactFactorLookup

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "items": [
                    {
                        "title": "Archives of biochemistry and biophysics impact factor",
                        "snippet": "Archives of Biochemistry and Biophysics Journal Impact Factor 2024 is 12.4 according to search snippets.",
                        "link": "https://example.test/archives-if",
                    }
                ]
            }

    class _Session:
        def __init__(self):
            self.calls = 0

        def get(self, *_args, **_kwargs):
            self.calls += 1
            return _Response()

    session = _Session()
    lookup = GoogleCustomSearchImpactFactorLookup(
        api_key="google-key",
        search_engine_id="cse-id",
        cache_dir=tmp_path,
        session=session,  # type: ignore[arg-type]
    )

    first = lookup.lookup("Archives of biochemistry and biophysics")
    second = lookup.lookup("Archives of biochemistry and biophysics")

    assert first.value == 12.4
    assert first.year == 2024
    assert first.trust_label.value == "public_candidate"
    assert first.source == "Google Custom Search snippet"
    assert first.source_url == "https://example.test/archives-if"
    assert second.value == 12.4
    assert session.calls == 1


def test_configured_csv_takes_priority_over_google_candidate(tmp_path):
    from pubmed_tool.if_lookup import FixtureImpactFactorLookup, GoogleCustomSearchImpactFactorLookup

    csv_path = tmp_path / "if.csv"
    csv_path.write_text(
        "journal,impact_factor,year,source,trust,status\n"
        "Archives of biochemistry and biophysics,15.1,2024,JCR licensed export,official,known\n",
        encoding="utf-8",
    )

    class _Session:
        def get(self, *_args, **_kwargs):
            raise AssertionError("Google fallback should not be called when CSV matches")

    lookup = FixtureImpactFactorLookup(
        data_path=csv_path,
        fallback_lookup=GoogleCustomSearchImpactFactorLookup(
            api_key="google-key",
            search_engine_id="cse-id",
            cache_dir=tmp_path,
            session=_Session(),  # type: ignore[arg-type]
        ),
    )

    evidence = lookup.lookup("Archives of biochemistry and biophysics")

    assert evidence.value == 15.1
    assert evidence.trust_label.value == "official"
