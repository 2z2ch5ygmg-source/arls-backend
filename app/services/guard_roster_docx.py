from __future__ import annotations

from difflib import SequenceMatcher
import re
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from docx import Document
from ..utils.address_norm import normalize_address_text

DATE_PATTERN = re.compile(r"(?P<year>\d{2,4})\s*[./-]\s*(?P<month>\d{1,2})\s*[./-]\s*(?P<day>\d{1,2})")
PHONE_PATTERN = re.compile(r"(01[016789])[-\s]?(\d{3,4})[-\s]?(\d{4})")
MGMT_NO_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)?")
SITE_HINT_SPLIT_PATTERN = re.compile(r"[\r\n/|,;]+")

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    # 경비원명부 라벨 고정 파서 (요구사항 기준 9개)
    "management_no": ("관리번호", "관리 번호"),
    "name": ("성명", "성 명"),
    "address": ("주소",),
    "placement_text": ("배치지", "배치 지"),
    "birthdate": ("생년월일", "생년 월일"),
    "phone": ("전화번호", "전화 번호"),
    "training_cert_no": ("경비원 신임교육 이수증 교부번호", "교부번호", "교부 번호"),
    "hire_date": ("채용일", "채용 일"),
    "leave_date": ("퇴직일", "퇴직 일"),
}

IMAGE_EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _clean_text(value: str | None) -> str:
    text = str(value or "").replace("\u3000", " ").strip()
    return re.sub(r"\s+", " ", text).strip()


def _normalize_label(value: str | None) -> str:
    text = _clean_text(value).lower()
    return re.sub(r"[\s:：\-\[\]\(\)<>]+", "", text)


def _collect_docx_lines(document: Document) -> list[str]:
    lines: list[str] = []

    for paragraph in document.paragraphs:
        text = _clean_text(paragraph.text)
        if not text:
            continue
        for line in re.split(r"[\r\n]+", text):
            normalized = _clean_text(line)
            if normalized:
                lines.append(normalized)

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                text = _clean_text(cell.text)
                if not text:
                    continue
                for line in re.split(r"[\r\n]+", text):
                    normalized = _clean_text(line)
                    if normalized:
                        lines.append(normalized)

    return lines


def _collect_docx_pairs(document: Document) -> dict[str, str]:
    pairs: dict[str, str] = {}

    for table in document.tables:
        for row in table.rows:
            cells = [_clean_text(cell.text) for cell in row.cells]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue

            if len(cells) >= 2:
                key = _normalize_label(cells[0])
                val = _clean_text(cells[1])
                if key and val and key not in pairs:
                    pairs[key] = val

            if len(cells) >= 4:
                for idx in range(0, len(cells) - 1, 2):
                    key = _normalize_label(cells[idx])
                    val = _clean_text(cells[idx + 1])
                    if key and val and key not in pairs:
                        pairs[key] = val

    return pairs


def _pick_field_value(pairs: dict[str, str], lines: list[str], aliases: tuple[str, ...]) -> str:
    alias_keys = [_normalize_label(alias) for alias in aliases]

    for alias in alias_keys:
        if not alias:
            continue
        for key, value in pairs.items():
            if alias in key or key in alias:
                candidate = _clean_text(value)
                if candidate:
                    return candidate

    for line in lines:
        for alias in aliases:
            pattern = rf"{re.escape(alias)}\s*[:：]?\s*(.+)$"
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                candidate = _clean_text(match.group(1))
                if candidate:
                    return candidate
    return ""


def _normalize_date(value: str | None) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    match = DATE_PATTERN.search(text)
    if not match:
        return ""
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    if year < 100:
        year = year + 2000 if year < 50 else year + 1900
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def _normalize_phone(value: str | None) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    match = PHONE_PATTERN.search(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    digits = re.sub(r"\D+", "", text)
    if len(digits) in (10, 11):
        if len(digits) == 10:
            return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return text


def _normalize_management_no(value: str | None) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    match = MGMT_NO_PATTERN.search(text.replace(" ", ""))
    if match:
        return match.group(0)
    return text.replace(" ", "")


def parse_guard_roster_docx(docx_bytes: bytes) -> dict[str, str]:
    document = Document(BytesIO(docx_bytes))
    lines = _collect_docx_lines(document)
    pairs = _collect_docx_pairs(document)

    extracted: dict[str, str] = {}
    for field_name, aliases in FIELD_ALIASES.items():
        extracted[field_name] = _pick_field_value(pairs, lines, aliases)

    extracted["management_no"] = _normalize_management_no(extracted.get("management_no"))
    # management_no 문자열을 그대로 보존(leading zero 유지)하기 위한 명시 필드
    extracted["management_no_str"] = extracted["management_no"]
    extracted["name"] = _clean_text(extracted.get("name"))
    extracted["birthdate"] = _normalize_date(extracted.get("birthdate"))
    extracted["hire_date"] = _normalize_date(extracted.get("hire_date"))
    extracted["leave_date"] = _normalize_date(extracted.get("leave_date"))
    extracted["phone"] = _normalize_phone(extracted.get("phone"))
    extracted["address"] = _clean_text(extracted.get("address"))
    extracted["placement_text"] = _clean_text(extracted.get("placement_text"))
    extracted["training_cert_no"] = _clean_text(extracted.get("training_cert_no"))
    return extracted


def extract_primary_docx_photo(docx_bytes: bytes) -> tuple[bytes | None, str | None, str | None]:
    try:
        with ZipFile(BytesIO(docx_bytes)) as archive:
            images: list[tuple[int, bytes, str, str]] = []
            for info in archive.infolist():
                filename = str(info.filename or "")
                if not filename.startswith("word/media/"):
                    continue
                ext = Path(filename).suffix.lower()
                if ext not in IMAGE_EXT_TO_MIME:
                    continue
                data = archive.read(info)
                if not data:
                    continue
                images.append((len(data), data, IMAGE_EXT_TO_MIME[ext], Path(filename).name))
    except (BadZipFile, KeyError):
        return None, None, None

    if not images:
        return None, None, None
    images.sort(key=lambda item: item[0], reverse=True)
    _, payload, mime, filename = images[0]
    return payload, mime, filename


def _build_site_hint_text(*, placement_text: str, address_text: str) -> str:
    fragments: list[str] = []
    for raw in (_clean_text(placement_text), _clean_text(address_text)):
        if not raw:
            continue
        for chunk in SITE_HINT_SPLIT_PATTERN.split(raw):
            normalized = _clean_text(chunk)
            if normalized:
                fragments.append(normalized)
    if not fragments:
        return ""
    # 순서를 유지한 중복 제거
    deduped: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        key = fragment.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fragment)
    return " ".join(deduped)


def _sequence_similarity(a: str, b: str) -> float:
    left = str(a or "").strip()
    right = str(b or "").strip()
    if not left or not right:
        return 0.0
    return float(SequenceMatcher(None, left, right).ratio())


def _site_match_score(*, query_norm: str, site_name: str, address_norm: str) -> float:
    if not query_norm:
        return 0.0
    addr_score = _sequence_similarity(query_norm, address_norm)
    name_score = _sequence_similarity(query_norm, normalize_address_text(site_name))
    # 주소 기반을 우선하고, 현장명 힌트를 보조 점수로 반영
    return round(min(1.0, (addr_score * 0.85) + (name_score * 0.15)), 4)


def match_site_candidates(
    *,
    placement_text: str,
    address_text: str = "",
    sites: list[dict],
    threshold: float = 0.86,
    top_n: int = 3,
) -> dict[str, object]:
    query_norm = normalize_address_text(
        _build_site_hint_text(placement_text=placement_text, address_text=address_text)
    )
    ranked: list[dict[str, object]] = []
    for site in sites:
        site_code = _clean_text(site.get("site_id") or site.get("site_code"))
        site_name = _clean_text(site.get("site_name"))
        site_address = _clean_text(site.get("address_text") or site.get("address"))
        site_address_norm = _clean_text(site.get("address_norm")) or normalize_address_text(site_address)
        score = _site_match_score(
            query_norm=query_norm,
            site_name=site_name,
            address_norm=site_address_norm,
        )
        ranked.append(
            {
                "site_id": site_code,
                "site_code": site_code,
                "site_name": site_name or site_code,
                "score": round(float(score), 3),
            }
        )

    ranked.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    candidates = ranked[: max(1, int(top_n or 3))]
    best = candidates[0] if candidates else None
    best_score = float(best.get("score") or 0) if best else 0.0
    auto_site_code = str(best.get("site_code") or "").strip() if best else ""
    auto_site_name = str(best.get("site_name") or "").strip() if best else ""

    status = "READY" if auto_site_code and best_score >= float(threshold) else "NEEDS_SITE_PICK"
    return {
        "site_code": auto_site_code if status == "READY" else "",
        "site_name": auto_site_name if status == "READY" else "",
        "confidence": round(best_score, 3),
        "candidates": candidates,
        "status": status,
    }


def build_employee_code_from_management_no(site_code: str, management_no: str) -> str:
    left = _clean_text(site_code).upper()
    right = _clean_text(management_no)
    if not left or not right:
        return ""
    return f"{left}-{right}"
