# backend/app/scripts/enrichment/paths.py
"""source 경로 정규화 및 경로 기반 분류 유틸.

raw 데이터의 `source`는 Windows 백슬래시(`src\\content\\...`)지만, 소비처와
과거 가공본은 forward-slash 소문자 `source_path`를 기대한다. 정규화 기준을
이 모듈 한 곳으로 통일한다.
"""

import re


def normalize_source(source: str) -> str:
    """`source`(백슬래시 가능) → 정규화된 `source_path`(forward-slash 소문자)."""
    return source.replace("\\", "/").lower().strip()


def top_section(source_path: str) -> str:
    """`src/content/<section>/...` 에서 <section>(learn/reference/blog/warnings) 반환."""
    parts = [p for p in re.split(r"[\\/]+", source_path) if p]
    if "content" in parts:
        idx = parts.index("content")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def reference_subsection(source_path: str) -> str:
    """`.../reference/<sub>/...` 에서 <sub>(react/react-dom/rsc/rules) 반환."""
    parts = [p for p in re.split(r"[\\/]+", source_path) if p]
    if "reference" in parts:
        idx = parts.index("reference")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def filename(source_path: str) -> str:
    """경로의 마지막 세그먼트(파일명) 반환."""
    parts = [p for p in re.split(r"[\\/]+", source_path) if p]
    return parts[-1] if parts else ""
