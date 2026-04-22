from __future__ import annotations

from fastapi.testclient import TestClient

from pubmed_tool.app import FixturePubMedClient, create_app
from pubmed_tool.models import OaResource, PaperRecord
from pubmed_tool.search import SearchOrchestrator


class _PmcClient:
    def __init__(self, resource: OaResource | None) -> None:
        self.resource = resource

    def get_resource(self, _pmcid: str | None) -> OaResource | None:
        return self.resource


class _PdfFetcher:
    def __init__(self, content: bytes | Exception) -> None:
        self.content = content
        self.urls: list[str] = []

    def fetch_pdf(self, url: str) -> bytes:
        self.urls.append(url)
        if isinstance(self.content, Exception):
            raise self.content
        return self.content


def _paper() -> PaperRecord:
    return PaperRecord(
        pmid="2001",
        title="Protein biomarker PDF study",
        journal="Journal of Fixture Medicine",
        year="2025",
        pmcid="PMC2001",
        abstract="Protein abstract fallback text.",
        links={"pubmed": "https://pubmed.ncbi.nlm.nih.gov/2001/"},
    )


def _search(client: TestClient) -> dict:
    expansions = client.post("/api/pubmed/expansions", json={"question": "protein biomarker"}).json()["expansions"]
    response = client.post(
        "/api/pubmed/search",
        json={"question": "protein biomarker", "expansions": expansions, "impact_factor_threshold": 10, "max_results": 50},
    )
    assert response.status_code == 200
    return response.json()


def test_pmc_oa_pdf_success_earns_pdf_basis_and_structured_provenance():
    fetcher = _PdfFetcher(b"%PDF-1.4\nProtein biomarker full text PDF evidence for sepsis.\n%%EOF\n")
    orchestrator = SearchOrchestrator(
        pubmed_client=FixturePubMedClient([_paper()]),
        pmc_client=_PmcClient(OaResource(pmcid="PMC2001", pdf_url="https://pmc.example/pdf", license="CC BY")),
        pdf_fetcher=fetcher,
    )
    client = TestClient(create_app(orchestrator=orchestrator))

    payload = _search(client)
    row = payload["results"][0]
    detail = client.get(f"/api/pubmed/results/{payload['job_id']}/papers/{row['pmid']}").json()

    assert fetcher.urls == ["https://pmc.example/pdf"]
    assert row["text_evidence_basis"] == "pmc_pdf"
    assert row["evidence_label"] == "PDF 원문 기반 평가입니다."
    assert detail["pdf_details"]["status"] == "analyzed"
    assert detail["pdf_details"]["evidence_basis"] == "pmc_pdf"
    assert detail["provenance"]["relevance"] == "pmc_pdf"
    assert detail["provenance"]["keywords"] == "pmc_pdf"
    assert detail["provenance"]["summary"] == "pmc_pdf"
    assert detail["provenance"]["impact_factor"]["trust_label"] == "official"


def test_pmc_oa_pdf_failure_falls_back_to_abstract_with_failure_label():
    orchestrator = SearchOrchestrator(
        pubmed_client=FixturePubMedClient([_paper()]),
        pmc_client=_PmcClient(OaResource(pmcid="PMC2001", pdf_url="https://pmc.example/pdf", license="CC BY")),
        pdf_fetcher=_PdfFetcher(RuntimeError("fixture download failed")),
    )
    client = TestClient(create_app(orchestrator=orchestrator))

    payload = _search(client)
    detail = client.get(f"/api/pubmed/results/{payload['job_id']}/papers/2001").json()

    assert detail["text_evidence_basis"] == "pdf_failed_fallback"
    assert detail["evidence_label"] == "원문 분석 실패. abstract 기준으로만 평가했습니다."
    assert detail["pdf_details"]["status"] == "failed"
    assert detail["provenance"]["relevance"] == "pdf_failed_fallback"


def test_authenticated_pdf_json_policy_rejects_session_and_login_variants():
    client = TestClient(create_app())

    banned_payloads = [
        {"username": "researcher@example.com"},
        {"credentials": {"user": "researcher"}},
        {"login_instructions": "open institutional proxy"},
        {"session_material": "abc"},
        {"notes": "no file here"},
    ]
    for payload in banned_payloads:
        response = client.post("/api/pubmed/results/job/papers/pmid/authenticated-pdf", json=payload)
        assert response.status_code == 400


def test_resolve_access_dict_without_abstract_attribute_does_not_crash():
    from pubmed_tool.access import resolve_access

    access = resolve_access({"pmid": "no-abstract"})

    assert access.text_evidence_basis.value == "metadata_only"
    assert access.access_status.value == "unknown"
