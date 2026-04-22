from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from pubmed_tool.config import PubMedToolSettings
from pubmed_tool.app import FixturePubMedClient, create_app
from pubmed_tool.models import PaperRecord
from pubmed_tool.pubmed_client import PubMedClient, RateLimiter
from pubmed_tool.search import SearchOrchestrator

from fastapi.testclient import TestClient


class _Response:
    status_code = 200
    text = """<?xml version="1.0" encoding="UTF-8"?>
    <eSearchResult><IdList><Id>123</Id></IdList></eSearchResult>
    """

    def raise_for_status(self) -> None:
        return None


class _Session:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *_args, **_kwargs) -> _Response:
        self.calls += 1
        return _Response()


def test_rate_limiter_serializes_parallel_waits():
    limiter = RateLimiter(requests_per_second=40)
    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda _index: limiter.wait(), range(5)))

    elapsed = time.monotonic() - started
    assert elapsed >= (4 * (1 / 40)) * 0.85


def test_pubmed_client_caches_eutils_xml_and_records_observability(tmp_path):
    session = _Session()
    settings = PubMedToolSettings(
        ncbi_tool="test-tool",
        ncbi_email="dev@example.test",
        cache_dir=tmp_path,
    )
    client = PubMedClient(settings=settings, session=session)  # type: ignore[arg-type]

    assert client.search_pmids("protein", max_results=1) == ["123"]
    assert client.search_pmids("protein", max_results=1) == ["123"]

    assert session.calls == 1
    assert client.metrics[0]["cache_hit"] is False
    assert client.metrics[0]["service"] == "ncbi_eutils"
    assert "rate_limit_wait" in client.metrics[0]
    assert client.metrics[1]["cache_hit"] is True
    assert client.metrics[1]["cache_path"] == client.metrics[0]["cache_path"]
    assert client.metrics[0]["request_id"]


def test_search_metrics_include_required_observability_fields_and_unknown_if_count():
    papers = [
        PaperRecord(
            pmid="3001",
            title="Protein evidence",
            journal="Journal of Fixture Medicine",
            year="2025",
            abstract="protein biomarker evidence",
        ),
        PaperRecord(
            pmid="3002",
            title="Unknown journal evidence",
            journal="Missing Journal",
            year="2025",
            abstract="protein evidence from an unknown journal",
        ),
    ]
    orchestrator = SearchOrchestrator(pubmed_client=FixturePubMedClient(papers))
    client = TestClient(create_app(orchestrator=orchestrator))

    response = client.post(
        "/api/pubmed/search",
        json={"question": "protein evidence", "expansions": [], "impact_factor_threshold": 10, "max_results": 50},
    )

    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics["request_id"]
    assert metrics["job_id"] == response.json()["job_id"]
    assert len(metrics["query_hash"]) == 64
    assert metrics["missing_source_label_count"] == 0
    assert metrics["if_trust_counts"]["official"] == 1
    assert metrics["if_trust_counts"]["unknown"] == 1


def test_search_job_external_metrics_are_scoped_per_job(tmp_path):
    session = _Session()
    settings = PubMedToolSettings(
        ncbi_tool="test-tool",
        ncbi_email="dev@example.test",
        cache_dir=tmp_path,
    )
    pubmed_client = PubMedClient(settings=settings, session=session)  # type: ignore[arg-type]
    orchestrator = SearchOrchestrator(pubmed_client=pubmed_client)

    first = orchestrator.run_search("protein evidence", [], max_results=1)
    second = orchestrator.run_search("protein evidence", [], max_results=1)

    assert first.metrics["job_id"] != second.metrics["job_id"]
    assert {item["job_id"] for item in first.metrics["external_requests"]} == {first.metrics["job_id"]}
    assert {item["job_id"] for item in second.metrics["external_requests"]} == {second.metrics["job_id"]}
    assert {item["request_id"] for item in first.metrics["external_requests"]} == {first.metrics["request_id"]}
    assert {item["request_id"] for item in second.metrics["external_requests"]} == {second.metrics["request_id"]}
    assert len(first.metrics["external_requests"]) == len(second.metrics["external_requests"])
    assert second.metrics["cache_hits"] == len(second.metrics["external_requests"])
