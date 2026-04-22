from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

from pubmed_tool.app import FixturePubMedClient, create_app
from pubmed_tool.llm_provider import (
    LlmProviderError,
    QueryConcept,
    QueryPlan,
    SuggestedFilters,
    validate_query_plan,
    validate_summary_keywords,
)
from pubmed_tool.models import AnalysisResult, EVIDENCE_LABELS, PaperRecord, TextEvidenceBasis
from pubmed_tool.search import SearchOrchestrator


class _QueryPlannerProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def plan_query(self, question: str, filters: dict) -> QueryPlan:
        self.calls.append({"question": question, "filters": filters})
        return QueryPlan(
            english_query="secreted proteins in human disease",
            concepts=[
                QueryConcept(
                    original="분비단백질",
                    candidates=["secreted protein", "secretome", "extracellular protein", "signal peptide"],
                )
            ],
            suggested_filters=SuggestedFilters(access="all"),
            provider="openai",
        )

    def summarize_keywords(self, text: str, basis: TextEvidenceBasis) -> AnalysisResult:
        return AnalysisResult(
            relevance_score=0,
            keywords=["secreted protein", "secretome"],
            summary=f"LLM summary for {text[:24]}",
            text_evidence_basis=basis,
            evidence_label=EVIDENCE_LABELS[basis],
            provenance={"relevance": basis.value, "summary": basis.value, "keywords": basis.value},
            summary_label="LLM 생성 요약",
            keywords_label="LLM 추출 키워드",
            analysis_provider="openai",
        )


def test_expansions_endpoint_uses_openai_query_planner_for_korean_sentence(tmp_path):
    provider = _QueryPlannerProvider()
    app = create_app()
    app.state.llm_provider = provider
    app.state.llm_cache.cache_dir = tmp_path
    client = TestClient(app)

    response = client.post(
        "/api/pubmed/expansions",
        json={
            "question": "분비단백질 관련한 연구 논문을 찾고싶어",
            "filters": {"access": "all"},
            "llm_enabled": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    candidates = {item["synonym"] for item in payload["expansions"]}
    assert {"secreted protein", "secretome", "extracellular protein", "signal peptide"} <= candidates
    assert provider.calls == [{"question": "분비단백질 관련한 연구 논문을 찾고싶어", "filters": {"access": "all"}}]


def test_cell_division_korean_query_has_local_candidate_terms_when_openai_unavailable():
    client = TestClient(create_app())

    response = client.post(
        "/api/pubmed/expansions",
        json={"question": "세포의 분열에 대한 논문이 필요함", "filters": {}, "llm_enabled": True},
    )

    assert response.status_code == 200
    candidates = {item["synonym"] for item in response.json()["expansions"]}
    assert {"cell division", "mitosis", "cytokinesis", "cell cycle"} <= candidates


def test_magnetic_field_korean_query_has_local_candidate_terms_when_openai_unavailable():
    client = TestClient(create_app())

    response = client.post(
        "/api/pubmed/expansions",
        json={"question": "자기장 관련된 논문 검색해줘", "filters": {}, "llm_enabled": True},
    )

    assert response.status_code == 200
    payload = response.json()
    candidates = {item["synonym"] for item in payload["expansions"]}
    assert payload["english_query"] == "magnetic field"
    assert {"magnetic field", "magnetic fields", "electromagnetic fields", "static magnetic field"} <= candidates


def test_human_keyword_query_has_pubmed_candidate_terms_when_openai_unavailable():
    client = TestClient(create_app())

    response = client.post(
        "/api/pubmed/expansions",
        json={"question": "human", "filters": {}, "llm_enabled": True},
    )

    assert response.status_code == 200
    payload = response.json()
    candidates = {item["synonym"] for item in payload["expansions"]}
    assert payload["english_query"] == "humans"
    assert {"humans", "human subjects", "human studies", "human cells"} <= candidates


def test_search_can_continue_without_expansion_suggestions_using_english_query():
    papers = [
        PaperRecord(
            pmid="plain-search",
            title="Mitosis and cell cycle control",
            journal="Journal of Fixture Medicine",
            year="2025",
            abstract="Mitosis and cell cycle checkpoints regulate cell division.",
        )
    ]
    orchestrator = SearchOrchestrator(pubmed_client=FixturePubMedClient(papers), llm_summary_limit=0)

    job = orchestrator.run_search(
        "세포의 분열에 대한 논문이 필요함",
        [],
        english_query="cell division mitosis cell cycle",
        llm_enabled=False,
    )

    assert "cell division" in job.query
    assert job.results[0].relevance_score > 0


def test_relevance_score_uses_title_when_abstract_omits_query_terms():
    papers = [
        PaperRecord(
            pmid="title-match",
            title="Static magnetic field therapy for disc degeneration",
            journal="Journal of Fixture Medicine",
            year="2025",
            abstract="Intervertebral disc degeneration involves mitochondrial dysfunction in nucleus pulposus cells.",
        )
    ]
    orchestrator = SearchOrchestrator(pubmed_client=FixturePubMedClient(papers), llm_summary_limit=0)

    job = orchestrator.run_search("magnetic field", [], llm_enabled=False)

    assert job.results[0].relevance_score > 0


def test_expansions_endpoint_sanitizes_filters_before_openai_provider(tmp_path):
    provider = _QueryPlannerProvider()
    app = create_app()
    app.state.llm_provider = provider
    app.state.llm_cache.cache_dir = tmp_path
    client = TestClient(app)

    response = client.post(
        "/api/pubmed/expansions",
        json={
            "question": "분비단백질 관련한 연구 논문을 찾고싶어",
            "filters": {
                "access": "all",
                "year_from": 2020,
                "token": "secret",
                "cookie": "session=abc",
                "url": "https://institution.example/private",
                "nested": {"credentials": "hidden"},
            },
            "llm_enabled": True,
        },
    )

    assert response.status_code == 200
    assert provider.calls[0]["filters"] == {"access": "all", "year_from": 2020}


def test_expansions_endpoint_preserves_safe_ui_filter_aliases(tmp_path):
    provider = _QueryPlannerProvider()
    app = create_app()
    app.state.llm_provider = provider
    app.state.llm_cache.cache_dir = tmp_path
    client = TestClient(app)

    response = client.post(
        "/api/pubmed/expansions",
        json={
            "question": "분비단백질 관련한 연구 논문을 찾고싶어",
            "filters": {
                "minRelevance": 25,
                "minIf": 10,
                "trust": "official",
                "yearStart": 2020,
                "yearEnd": 2026,
                "keywordInclude": "secretome",
                "keywordExclude": "mouse",
                "token": "secret",
                "url": "https://institution.example/private",
            },
            "llm_enabled": True,
        },
    )

    assert response.status_code == 200
    assert provider.calls[0]["filters"] == {
        "min_relevance": 25,
        "impact_factor_threshold": 10,
        "if_trust": "official",
        "year_from": 2020,
        "year_to": 2026,
        "keyword_include": "secretome",
        "keyword_exclude": "mouse",
    }


def test_expansions_endpoint_falls_back_when_llm_disabled():
    provider = _QueryPlannerProvider()
    app = create_app()
    app.state.llm_provider = provider
    client = TestClient(app)

    response = client.post(
        "/api/pubmed/expansions",
        json={"question": "분비단백질 관련한 연구 논문을 찾고싶어", "filters": {}, "llm_enabled": False},
    )

    assert response.status_code == 200
    assert provider.calls == []
    assert any(item["synonym"] == "secreted protein" for item in response.json()["expansions"])


def test_structured_output_validation_rejects_malformed_payloads():
    try:
        validate_query_plan({"english_query": "", "concepts": [], "suggested_filters": {}}, provider="openai")
    except LlmProviderError:
        pass
    else:
        raise AssertionError("empty candidates must fail query plan validation")

    try:
        validate_summary_keywords({"one_line_summary": "ok", "keywords": "not-array"}, basis=TextEvidenceBasis.ABSTRACT_ONLY)
    except LlmProviderError:
        pass
    else:
        raise AssertionError("non-array keywords must fail summary validation")


def test_search_uses_llm_summary_for_top_10_only_and_fallback_after_that():
    provider = _QueryPlannerProvider()
    papers = [
        PaperRecord(
            pmid=str(index),
            title=f"Secreted protein paper {index}",
            journal="Journal of Fixture Medicine",
            year="2025",
            abstract=f"Secreted protein abstract {index}",
        )
        for index in range(12)
    ]
    orchestrator = SearchOrchestrator(
        pubmed_client=FixturePubMedClient(papers),
        llm_provider=provider,
        llm_summary_limit=10,
    )

    job = orchestrator.run_search("secreted protein", [], llm_enabled=True)

    providers = [result.analysis_provider for result in job.results]
    assert providers.count("openai") == 10
    assert providers.count("local_fallback") == 2
    assert job.metrics["llm_summary_count"] == 10
    assert job.metrics["local_fallback_count"] == 2


def test_korean_query_relevance_uses_selected_english_candidates():
    papers = [
        PaperRecord(
            pmid="cell-division",
            title="Cell division and cytokinesis in epithelial cells",
            journal="Journal of Fixture Medicine",
            year="2025",
            abstract="Cell division, mitosis, and cytokinesis coordinate the cell cycle.",
        )
    ]
    expansions = [
        QueryConcept(
            original="세포 분열",
            candidates=["cell division", "mitosis", "cytokinesis", "cell cycle"],
        )
    ]
    selected = QueryPlan(english_query="cell division", concepts=expansions, suggested_filters=SuggestedFilters()).to_expansions()
    orchestrator = SearchOrchestrator(pubmed_client=FixturePubMedClient(papers), llm_summary_limit=0)

    job = orchestrator.run_search("세포의 분열에 대한 논문이 필요함", selected, llm_enabled=False)

    assert job.results[0].relevance_score > 0


def test_llm_summary_overlays_only_summary_keywords_not_relevance_or_evidence():
    provider = _QueryPlannerProvider()
    papers = [
        PaperRecord(
            pmid="keep-relevance",
            title="Secreted protein biomarker",
            journal="Journal of Fixture Medicine",
            year="2025",
            abstract="secreted protein biomarker evidence",
        )
    ]
    orchestrator = SearchOrchestrator(
        pubmed_client=FixturePubMedClient(papers),
        llm_provider=provider,
        llm_summary_limit=10,
    )

    job = orchestrator.run_search("secreted protein biomarker", [], llm_enabled=True)
    result = job.results[0]

    assert result.analysis_provider == "openai"
    assert result.relevance_score > 0
    assert result.evidence_label == EVIDENCE_LABELS[TextEvidenceBasis.ABSTRACT_ONLY]
    assert result.provenance["relevance"] == "abstract_only"
    assert result.summary.startswith("LLM summary")


def test_llm_summary_regenerate_endpoint_updates_selected_paper_only_and_preserves_relevance():
    provider = _QueryPlannerProvider()
    papers = [
        PaperRecord(
            pmid="one",
            title="Secreted protein first",
            journal="Journal of Fixture Medicine",
            year="2025",
            abstract="secreted protein biomarker evidence",
        ),
        PaperRecord(
            pmid="two",
            title="Secreted protein second",
            journal="Journal of Fixture Medicine",
            year="2025",
            abstract="secreted protein biomarker second evidence",
        ),
    ]
    orchestrator = SearchOrchestrator(pubmed_client=FixturePubMedClient(papers), llm_summary_limit=0)
    app = create_app(orchestrator=orchestrator)
    app.state.orchestrator.llm_provider = provider
    client = TestClient(app)
    response = client.post(
        "/api/pubmed/search",
        json={"question": "secreted protein biomarker", "expansions": [], "impact_factor_threshold": 10, "max_results": 50},
    )
    job_id = response.json()["job_id"]
    before = {row["pmid"]: row for row in response.json()["results"]}
    regenerate = client.post(f"/api/pubmed/results/{job_id}/papers/one/llm-summary", json={"llm_enabled": True})

    assert regenerate.status_code == 200
    updated = regenerate.json()
    assert updated["analysis_provider"] == "openai"
    assert updated["summary_label"] == "LLM 생성 요약"
    assert updated["evidence_label"] == EVIDENCE_LABELS[TextEvidenceBasis.ABSTRACT_ONLY]
    assert updated["relevance_score"] == before["one"]["relevance_score"]
    other = client.get(f"/api/pubmed/results/{job_id}/papers/two").json()
    assert other["analysis_provider"] == "local_fallback"


def test_static_ui_hides_suggestion_rationale_source_and_pdf_upload():
    index = Path("pubmed_tool/static/index.html").read_text(encoding="utf-8")
    app_js = Path("pubmed_tool/static/app.js").read_text(encoding="utf-8")

    assert "Upload authenticated PDF bytes" not in index
    assert "pdf-form" not in index
    assert "pdf-file" not in index
    assert "Source:" not in app_js
    assert "expansion-rationale" not in app_js
    assert "llm-enabled" in index
    assert "llm-regenerate" in index
