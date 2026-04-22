from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


ABSTRACT_LABEL = "Abstract 기반 평가입니다. 원문 결론은 확인하지 않았습니다."
AUTHENTICATED_PDF_LABEL = "사용자 인증 접근 PDF 기반 평가입니다."
PDF_FAILED_LABEL = "원문 분석 실패. abstract 기준으로만 평가했습니다."


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if is_dataclass(value):
        return asdict(value)
    return value


def _field(value: Any, name: str) -> Any:
    value = _to_plain(value)
    if isinstance(value, dict):
        return value[name]
    return getattr(value, name)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _enum_member(enum_cls: type, expected_value: str) -> Any:
    for member in enum_cls:
        if getattr(member, "value", None) == expected_value or getattr(member, "name", "").lower() == expected_value:
            return member
    raise AssertionError(f"{enum_cls.__name__} is missing {expected_value!r}")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _rows_from_payload(payload: Any) -> list[Any]:
    payload = _to_plain(payload)
    if isinstance(payload, list):
        return payload
    for key in ("rows", "results", "papers", "items"):
        if isinstance(payload, dict) and key in payload:
            return payload[key]
    raise AssertionError(f"payload does not contain result rows: {payload!r}")


def test_pubmed_tool_modules_do_not_import_arls_app_modules():
    package = importlib.import_module("pubmed_tool")
    package_paths = list(getattr(package, "__path__", []))
    assert package_paths, "pubmed_tool must be a standalone package"
    repo_root = Path.cwd().resolve()
    assert any(_is_relative_to(Path(path).resolve(), repo_root) for path in package_paths), (
        "pubmed_tool must resolve to the local standalone package, "
        f"not an installed package at {package_paths!r}"
    )

    forbidden_roots = {
        "app.db",
        "app.deps",
        "app.security",
        "app.main",
        "app.routers",
        "app.services",
    }
    violations: list[str] = []

    for module_info in pkgutil.walk_packages(package_paths, prefix="pubmed_tool."):
        spec = importlib.util.find_spec(module_info.name)
        if spec is None or spec.origin is None or not spec.origin.endswith(".py"):
            continue
        tree = ast.parse(Path(spec.origin).read_text(encoding="utf-8"), filename=spec.origin)
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            for module_name in imported:
                if module_name == "app" or any(
                    module_name == root or module_name.startswith(f"{root}.") for root in forbidden_roots
                ):
                    violations.append(f"{module_info.name} imports {module_name}")

    assert violations == []


def test_recommend_expansions_returns_visible_toggleable_protein_polypeptide_synonym():
    from pubmed_tool.query_expansion import recommend_expansions

    expansions = [_to_plain(item) for item in recommend_expansions("protein folding stability")]

    assert expansions, "recommended expansions must be visible before search"
    assert any(
        {_field(item, "term").lower(), _field(item, "synonym").lower()} == {"protein", "polypeptide"}
        for item in expansions
    )
    for item in expansions:
        assert _field(item, "term")
        assert _field(item, "synonym")
        assert _field(item, "rationale") or _field(item, "source")
        assert isinstance(_field(item, "enabled"), bool)


def test_resolve_access_keeps_publisher_link_out_of_analyzed_text_basis():
    from pubmed_tool.access import resolve_access
    from pubmed_tool.models import AccessStatus, DownloadPermission, TextEvidenceBasis

    record = {
        "pmid": "1",
        "abstract": "Abstract text only.",
        "publisher_url": "https://publisher.example/paper",
    }

    access = resolve_access(record)

    assert _enum_value(_field(access, "access_status")) == _enum_value(_enum_member(AccessStatus, "publisher_link"))
    assert _enum_value(_field(access, "text_evidence_basis")) in {
        _enum_value(_enum_member(TextEvidenceBasis, "abstract_only")),
        _enum_value(_enum_member(TextEvidenceBasis, "metadata_only")),
    }
    assert _enum_value(_field(access, "download_permission")) in {
        _enum_value(_enum_member(DownloadPermission, "user_upload_required")),
        _enum_value(_enum_member(DownloadPermission, "forbidden")),
        _enum_value(_enum_member(DownloadPermission, "unknown")),
    }


def test_resolve_access_marks_pdf_failure_as_abstract_fallback_basis():
    from pubmed_tool.access import resolve_access
    from pubmed_tool.models import TextEvidenceBasis

    access = resolve_access({"pmid": "2", "abstract": "Fallback abstract."}, pdf_failed=True)

    assert _enum_value(_field(access, "text_evidence_basis")) == _enum_value(
        _enum_member(TextEvidenceBasis, "pdf_failed_fallback")
    )


def test_authenticated_pdf_endpoint_rejects_remote_url_and_credentials():
    from pubmed_tool.app import create_app

    client = TestClient(create_app())
    response = client.post(
        "/api/pubmed/results/job-1/papers/pmid-1/authenticated-pdf",
        json={
            "url": "https://publisher.example/authenticated.pdf",
            "username": "researcher@example.com",
            "password": "secret",
            "cookie": "session=abc",
            "token": "abc",
        },
    )

    assert response.status_code in {400, 422}
    assert "url" in response.text.lower() or "credential" in response.text.lower()


def test_authenticated_pdf_endpoint_accepts_uploaded_pdf_bytes_contract():
    from pubmed_tool.app import create_app

    client = TestClient(create_app())
    response = client.post(
        "/api/pubmed/results/job-1/papers/pmid-1/authenticated-pdf",
        files={"pdf": ("paper.pdf", b"%PDF-1.4\n% fixture\n%%EOF\n", "application/pdf")},
    )

    assert response.status_code < 400
    payload = response.json()
    assert AUTHENTICATED_PDF_LABEL in str(payload)
    assert "authenticated_pdf" in str(payload) or "user_uploaded_pdf" in str(payload)


def test_fixture_impact_factor_lookup_returns_all_trust_states_with_visible_unknown():
    from pubmed_tool.if_lookup import FixtureImpactFactorLookup
    from pubmed_tool.models import TrustLabel

    lookup = FixtureImpactFactorLookup(
        {
            "Official Journal": {
                "value": 12.4,
                "year": 2025,
                "source": "JCR fixture",
                "source_url": "https://example.test/jcr",
                "trust": "official",
            },
            "Unofficial Journal": {"value": 8.1, "year": 2025, "source": "fixture", "trust": "unofficial"},
            "Unverified Journal": {"value": 5.2, "year": 2025, "source": "fixture", "trust": "unverified"},
        }
    )

    official = lookup.lookup("Official Journal")
    unofficial = lookup.lookup("Unofficial Journal")
    unverified = lookup.lookup("Unverified Journal")
    unknown = lookup.lookup("Missing Journal")

    assert _enum_value(_field(official, "trust")) == _enum_value(_enum_member(TrustLabel, "official"))
    assert _enum_value(_field(unofficial, "trust")) == _enum_value(_enum_member(TrustLabel, "unofficial"))
    assert _enum_value(_field(unverified, "trust")) == _enum_value(_enum_member(TrustLabel, "unverified"))
    assert _field(unknown, "value") is None
    assert _enum_value(_field(unknown, "trust")) == _enum_value(_enum_member(TrustLabel, "unknown"))
    assert "unknown" in str(_to_plain(unknown)).lower()


def test_analyze_paper_provenance_uses_supplied_evidence_basis():
    from pubmed_tool.analysis import analyze_paper
    from pubmed_tool.models import TextEvidenceBasis

    analysis = analyze_paper(
        "protein folding stability",
        {"pmid": "3", "title": "Protein folding", "abstract": "Protein folding evidence."},
        "Protein folding evidence.",
        _enum_member(TextEvidenceBasis, "abstract_only"),
    )

    assert _field(analysis, "relevance_score") is not None
    assert _field(analysis, "keywords")
    assert _field(analysis, "summary")
    assert ABSTRACT_LABEL in str(_to_plain(analysis))
    assert "abstract_only" in str(_to_plain(analysis))


def test_search_flow_returns_relevance_sorted_fixture_rows_with_provenance_labels():
    from pubmed_tool.search import SearchOrchestrator

    rows = [
        {
            "pmid": str(index),
            "title": f"Protein fixture {index}",
            "journal": "Fixture Journal",
            "year": 2025,
            "abstract": "protein polypeptide folding evidence",
            "impact_factor": {"value": 11.0 if index % 2 else None, "trust": "official" if index % 2 else "unknown"},
            "access": {
                "text_evidence_basis": "abstract_only",
                "access_status": "abstract_only",
                "download_permission": "unknown",
            },
        }
        for index in range(1, 56)
    ]

    orchestrator = _build_search_orchestrator(SearchOrchestrator, rows)
    payload = _run_fixture_search(orchestrator, "protein folding", max_results=50)
    result_rows = _rows_from_payload(payload)

    assert len(result_rows) == 50
    scores = [_field(row, "relevance_score") for row in result_rows]
    assert scores == sorted(scores, reverse=True)
    for row in result_rows:
        serialized = str(_to_plain(row))
        assert _field(row, "pmid")
        assert "text_evidence_basis" in serialized
        assert "access_status" in serialized
        assert "download_permission" in serialized
        assert "trust" in serialized
        assert ABSTRACT_LABEL in serialized or PDF_FAILED_LABEL in serialized


def test_static_ui_assets_include_work_list_contract_markers_when_present():
    static_roots = [
        Path("pubmed_tool/static"),
        Path("pubmed_tool/ui"),
        Path("static/pubmed_tool"),
    ]
    files = [
        path
        for root in static_roots
        if root.exists()
        for path in root.rglob("*")
        if path.suffix.lower() in {".html", ".css", ".js", ".jsx", ".tsx", ".ts"}
    ]
    if not files:
        pytest.skip("PubMed UI static files are not present yet")

    corpus = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "PRIMARY_WHITE_PLANE" in corpus
    assert "Work List" in corpus or "work-list" in corpus or "workList" in corpus
    assert "열기" not in corpus
    assert "보기" not in corpus


def _build_search_orchestrator(orchestrator_cls: type, rows: list[dict[str, Any]]) -> Any:
    signature = inspect.signature(orchestrator_cls)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.default is not inspect.Parameter.empty:
            continue
        if name in {"pubmed_client", "client"}:
            kwargs[name] = _FixturePubMedClient(rows)
        elif name in {"if_lookup", "impact_factor_lookup"}:
            kwargs[name] = _FixtureIFLookup()
        elif name in {"analyzer", "analysis_engine"}:
            kwargs[name] = _FixtureAnalyzer()
        elif name in {"access_resolver", "access"}:
            kwargs[name] = _FixtureAccessResolver()
        else:
            kwargs[name] = None
    return orchestrator_cls(**kwargs)


def _run_fixture_search(orchestrator: Any, question: str, *, max_results: int) -> Any:
    for method_name in ("search", "run", "execute"):
        method = getattr(orchestrator, method_name, None)
        if method is None:
            continue
        signature = inspect.signature(method)
        kwargs: dict[str, Any] = {}
        if "question" in signature.parameters:
            kwargs["question"] = question
        if "query" in signature.parameters:
            kwargs["query"] = question
        if "max_results" in signature.parameters:
            kwargs["max_results"] = max_results
        if "limit" in signature.parameters:
            kwargs["limit"] = max_results
        if "selected_expansions" in signature.parameters:
            kwargs["selected_expansions"] = [{"term": "protein", "synonym": "polypeptide", "enabled": True}]
        if "if_threshold" in signature.parameters:
            kwargs["if_threshold"] = 10
        return method(**kwargs)
    raise AssertionError("SearchOrchestrator must expose search(), run(), or execute()")


class _FixturePubMedClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def search(self, *_args: Any, max_results: int = 50, **_kwargs: Any) -> list[dict[str, Any]]:
        return self.rows[:max_results]

    def fetch(self, pmids: list[str], **_kwargs: Any) -> list[dict[str, Any]]:
        wanted = set(pmids)
        return [row for row in self.rows if row["pmid"] in wanted]

    def search_and_fetch(self, *_args: Any, max_results: int = 50, **_kwargs: Any) -> list[dict[str, Any]]:
        return self.rows[:max_results]


class _FixtureIFLookup:
    def lookup(self, journal: str) -> dict[str, Any]:
        if "Fixture" in journal:
            return {
                "value": 11.0,
                "year": 2025,
                "source": "fixture",
                "source_url": "https://example.test/if",
                "trust": "official",
            }
        return {"value": None, "trust": "unknown"}


class _FixtureAnalyzer:
    def analyze(self, question: str, paper: dict[str, Any], evidence_text: str, basis: Any) -> dict[str, Any]:
        pmid = int(paper["pmid"])
        return {
            "relevance_score": 100 - pmid,
            "keywords": ["protein", "polypeptide", "folding"],
            "summary": f"{paper['title']} summary",
            "text_evidence_basis": _enum_value(basis),
            "evidence_label": ABSTRACT_LABEL,
        }


class _FixtureAccessResolver:
    def resolve(self, record: dict[str, Any], **_kwargs: Any) -> dict[str, str]:
        return {
            "text_evidence_basis": "abstract_only",
            "access_status": "abstract_only",
            "download_permission": "unknown",
        }
