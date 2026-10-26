from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Protocol

VECTOR_DIMENSIONS = 1024
MAX_CONTEXT_CHARACTERS = 3_400
_ASCII_WORD = re.compile(r"[a-z0-9][a-z0-9_.-]{1,63}")
_CODE = re.compile(r"\b(?:AI[356]\.\d|[DM][1-6](?:\.\d+)?)\b", re.IGNORECASE)
_ISSUE = re.compile(r"(?:#|issue\s*)(\d{1,8})", re.IGNORECASE)


class ChunkLike(Protocol):
    id: int
    source_type: str
    title: str
    content: str
    vector_json: dict
    metadata_json: dict
    rank_boost: float


@dataclass(frozen=True)
class RetrievalResult:
    source_id: str
    source_type: str
    title: str
    content: str
    metadata: dict[str, Any]
    score: float

    @property
    def page_url(self) -> str:
        return str(self.metadata.get("page_url", ""))

    @property
    def github_url(self) -> str:
        return str(self.metadata.get("github_url", ""))


def _normalise(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _features(text: str) -> list[str]:
    normalised = _normalise(text)
    compact = re.sub(r"\s+", "", normalised)
    features = [f"w:{word}" for word in _ASCII_WORD.findall(normalised)]
    for size in (2, 3):
        features.extend(
            f"g{size}:{compact[index:index + size]}"
            for index in range(max(0, len(compact) - size + 1))
        )
    return features


def embed_text(text: str, dimensions: int = VECTOR_DIMENSIONS) -> dict[str, float]:
    counts: dict[int, float] = {}
    for feature in _features(text):
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest, "big") % dimensions
        counts[bucket] = counts.get(bucket, 0.0) + 1.0
    weighted = {
        str(bucket): 1.0 + math.log(count)
        for bucket, count in counts.items()
        if count > 0
    }
    norm = math.sqrt(sum(value * value for value in weighted.values()))
    return (
        {bucket: value / norm for bucket, value in weighted.items()}
        if norm
        else {}
    )


def vector_similarity(left: dict, right: dict) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(float(value) * float(right.get(key, 0.0)) for key, value in left.items())


def _query_metadata(question: str) -> dict[str, Any]:
    normalised = _normalise(question)
    codes = {value.upper() for value in _CODE.findall(question)}
    issue_numbers = {int(value) for value in _ISSUE.findall(question)}
    domain_terms = (
        "issue",
        "pull request",
        "pr",
        "仓库",
        "报告",
        "问题",
        "指标",
        "评分",
        "健康度",
        "治理",
        "维护者",
        "标签",
        "闭环",
        "积压",
        "响应",
        "重复",
        "模板",
        "证据",
        "findings",
    )
    dimension_names = (
        "响应效率",
        "处理",
        "积压",
        "信息质量",
        "分类",
        "标签",
        "协作",
        "闭环",
        "知识",
        "沉淀",
    )
    return {
        "question": normalised,
        "codes": codes,
        "issue_numbers": issue_numbers,
        "domain_anchor": bool(codes or issue_numbers)
        or any(term in normalised for term in domain_terms)
        or any(term in normalised for term in dimension_names),
        "summary": any(
            word in normalised
            for word in ("总结", "概览", "整体", "总分", "健康度", "先说")
        ),
        "actions": any(
            word in normalised
            for word in ("优先", "先做", "下一步", "最该", "整改", "行动", "建议")
        ),
        "evidence": any(
            word in normalised
            for word in ("证据", "例子", "哪些issue", "哪些 issue", "来源")
        ),
        "duplicates": any(word in normalised for word in ("重复", "相似", "合并")),
        "definitions": any(
            word in normalised
            for word in ("怎么算", "如何计算", "定义", "含义", "阈值", "评分规则")
        ),
    }


def _score_chunk(
    question_vector: dict,
    chunk: ChunkLike,
    hints: dict[str, Any],
) -> float:
    vector_score = vector_similarity(question_vector, chunk.vector_json or {})
    metadata = chunk.metadata_json or {}
    score = vector_score + float(chunk.rank_boost or 0)
    codes = set(metadata.get("codes") or [])
    if hints["codes"] & codes:
        score += 0.42
    issue_number = metadata.get("issue_number")
    if issue_number in hints["issue_numbers"]:
        score += 0.6
    title = _normalise(chunk.title)
    content = _normalise(chunk.content)
    if hints["summary"] and chunk.source_type == "overview":
        score += 0.45
    if hints["actions"] and chunk.source_type in {"finding", "governance"}:
        score += 0.18
    if hints["evidence"]:
        if chunk.source_type == "evidence":
            score += 0.25
        elif chunk.source_type == "issue":
            score += 0.2
        elif chunk.source_type == "finding":
            score += 0.12
    if hints["duplicates"] and chunk.source_type == "duplicate":
        score += 0.2
    if hints["definitions"] and chunk.source_type == "guide":
        score += 0.18
    if any(code.lower() in title for code in hints["codes"]):
        score += 0.08
    if search_terms := metadata.get("search_terms"):
        if any(str(term).lower() in hints["question"] for term in search_terms):
            score += 0.08
    if not content:
        score -= 0.1
    return score


def retrieve_chunks(
    question: str,
    chunks: list[ChunkLike],
    *,
    limit: int = 8,
) -> list[RetrievalResult]:
    if not question.strip() or not chunks:
        return []
    hints = _query_metadata(question)
    if not hints["domain_anchor"]:
        return []
    question_vector = embed_text(question)
    ranked = sorted(
        (
            (
                _score_chunk(question_vector, chunk, hints),
                chunk,
            )
            for chunk in chunks
        ),
        key=lambda item: (-item[0], item[1].id),
    )
    selected: list[tuple[float, ChunkLike]] = []
    seen_keys: set[str] = set()
    for score, chunk in ranked:
        metadata = chunk.metadata_json or {}
        key = str(metadata.get("source_key") or chunk.id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        selected.append((score, chunk))
        if len(selected) >= limit:
            break
    if hints["summary"] and not any(item.source_type == "overview" for _, item in selected):
        overview = next((item for item in chunks if item.source_type == "overview"), None)
        if overview is not None:
            selected[-1] = (0.0, overview)
    return [
        RetrievalResult(
            source_id=str(chunk.id),
            source_type=chunk.source_type,
            title=chunk.title,
            content=chunk.content,
            metadata=chunk.metadata_json or {},
            score=round(score, 6),
        )
        for score, chunk in selected
    ]


def build_context(results: list[RetrievalResult]) -> str:
    blocks: list[str] = []
    used = 0
    for index, item in enumerate(results, start=1):
        block = (
            f"[K{index}] 类型：{item.source_type}；标题：{item.title}\n"
            f"{item.content}"
        )
        if used + len(block) > MAX_CONTEXT_CHARACTERS:
            remaining = MAX_CONTEXT_CHARACTERS - used
            if remaining > 120:
                blocks.append(block[:remaining])
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)
