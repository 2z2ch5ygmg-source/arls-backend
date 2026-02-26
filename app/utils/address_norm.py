from __future__ import annotations

import re

_MULTI_SPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^0-9a-zA-Z가-힣\s]")
_FLOOR_ROOM_PATTERNS = (
    re.compile(r"\b(?:b?\d{1,3}\s*f)\b", flags=re.IGNORECASE),
    re.compile(r"\bl\s*\d{1,2}\b", flags=re.IGNORECASE),
    re.compile(r"지하\s*\d{1,2}\s*층"),
    re.compile(r"\d{1,3}\s*층"),
    re.compile(r"\d{1,4}\s*호"),
)

_ADDRESS_REGION_REPLACEMENTS = (
    ("서울특별시", "서울"),
    ("부산광역시", "부산"),
    ("대구광역시", "대구"),
    ("인천광역시", "인천"),
    ("광주광역시", "광주"),
    ("대전광역시", "대전"),
    ("울산광역시", "울산"),
    ("세종특별자치시", "세종"),
    ("제주특별자치도", "제주"),
)

_ADDRESS_REMOVE_PATTERNS = (
    re.compile(r"\b(republic\s*of\s*korea)\b", flags=re.IGNORECASE),
    re.compile(r"\b(republic)\b", flags=re.IGNORECASE),
    re.compile(r"\b(korea)\b", flags=re.IGNORECASE),
    re.compile(r"대한민국"),
)

# 과도한 제거를 피하기 위해 stopword는 최소 적용 (행정 접두/층정보만)
_ADDRESS_STOPWORDS = (
    "특별시",
    "광역시",
    "층",
    "호",
)


def normalize_address_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""

    # 행정구역 표기를 최소한으로 정규화
    for source, target in _ADDRESS_REGION_REPLACEMENTS:
        text = text.replace(source.lower(), target.lower())

    # 국가명/영문 국가 표기 제거
    for pattern in _ADDRESS_REMOVE_PATTERNS:
        text = pattern.sub(" ", text)

    # 구분자 정리
    text = text.replace("-", " ")
    text = text.replace("_", " ")

    # 층/호/1F 류 상세 표기는 매칭 노이즈로 제거
    for pattern in _FLOOR_ROOM_PATTERNS:
        text = pattern.sub(" ", text)

    # 특수문자 제거
    text = _NON_WORD_RE.sub(" ", text)

    # stopword 제거 (토큰 단위)
    tokens = []
    for token in _MULTI_SPACE_RE.split(text):
        normalized = token.strip()
        if not normalized:
            continue
        if normalized in _ADDRESS_STOPWORDS:
            continue
        tokens.append(normalized)

    return " ".join(tokens)
