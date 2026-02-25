from __future__ import annotations

import re

_MULTI_SPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^0-9a-zA-Z가-힣\s]")

# 과도한 제거를 피하면서 주소 매칭 품질을 해치지 않는 최소 stopword만 적용
_ADDRESS_STOPWORDS = (
    "지점",
    "빌딩",
    "타워",
    "센터",
    "층",
)


def normalize_address_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""

    # 구분자 정리
    text = text.replace("-", " ")
    text = text.replace("_", " ")

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

