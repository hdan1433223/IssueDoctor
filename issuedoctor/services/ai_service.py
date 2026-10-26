import hashlib
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from flask import current_app

from issuedoctor.ai.batching import BatchItem, build_batches
from issuedoctor.ai.budget import effective_ai_budget
from issuedoctor.ai.client import OpenAICompatibleClient
from issuedoctor.ai.schemas import DuplicateReviewItem, IssueAnalysisItem
from issuedoctor.extensions import db
from issuedoctor.models import (
    AIAnalysis,
    AnalysisRun,
    DuplicateCandidate,
    EvidenceItem,
    Finding,
)
from issuedoctor.repositories.cache_repo import AICacheRepository
from issuedoctor.scoring.issue_quality import is_bug, is_low_information
from issuedoctor.security.secrets import LLM_API_KEY
from issuedoctor.services.config_service import load_yaml
from issuedoctor.services.settings_service import SettingsService


@dataclass(frozen=True)
class AIServiceResult:
    configured: bool
    eligible_count: int
    selected_count: int
    analyzed_count: int
    failed_batches: int
    api_call_count: int = 0
    skipped_count: int = 0
    duplicate_review_count: int = 0
    failure_reasons: tuple[str, ...] = ()
    budget_profile: str = "disabled"


class AIService:
    def __init__(self, client: OpenAICompatibleClient | None = None) -> None:
        self.client = client

    def analyze(self, run: AnalysisRun) -> AIServiceResult:
        settings_service = SettingsService()
        api_key = settings_service.secret_store.get(LLM_API_KEY)
        public = settings_service.get_public()
        if not api_key or not public.llm_model:
            run.ai_coverage_percent = 0
            run.ai_semantic_score = None
            run.ai_semantic_confidence = None
            run.enhanced_total_score = None
            db.session.commit()
            return AIServiceResult(False, len(run.issues), 0, 0, 0)

        analysis_config = load_yaml(current_app.config["ANALYSIS_CONFIG_PATH"])
        labels_config = load_yaml(current_app.config["LABELS_CONFIG_PATH"])
        requested_issues = (run.analysis_config_json or {}).get(
            "ai_requested_issue_count"
        )
        budget = effective_ai_budget(
            analysis_config,
            public.llm_base_url,
            requested_issues,
        )
        prompt_version = analysis_config["llm_prompt_version"]
        eligible = list(run.issues)
        selected = _select_issues(
            eligible,
            labels_config,
            budget["ai_max_issues"],
        )
        pending: list[BatchItem] = []
        cached_numbers: set[int] = set()
        pending_characters = 0
        analyzed = 0
        for issue in selected:
            cache_key = _cache_key(issue, prompt_version, public.llm_model)
            cached = AICacheRepository.get(cache_key)
            if cached:
                self._save_item(
                    run,
                    IssueAnalysisItem.model_validate(cached),
                    cache_key,
                    prompt_version,
                    public.llm_model,
                )
                cached_numbers.add(issue.issue_number)
                analyzed += 1
            else:
                item = BatchItem(
                    issue.issue_number,
                    issue.title[:300],
                    issue.body_excerpt[: budget["issue_body_max_chars"]],
                    {
                        "state": issue.state,
                        "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
                        "labels": [
                            value.get("name", "") if isinstance(value, dict) else str(value)
                            for value in issue.labels_json
                        ][:20],
                        "linked_pull_requests": issue.linked_pr_numbers_json[:20],
                    },
                )
                if (
                    pending_characters + item.character_count
                    > budget["ai_max_total_characters"]
                ):
                    continue
                pending.append(item)
                pending_characters += item.character_count

        batches = build_batches(
            pending,
            maximum_items=budget["llm_batch_issue_count"],
            maximum_characters=budget["llm_batch_total_chars"],
        )[: budget["ai_max_batches"]]
        scheduled_numbers = {
            item.issue_number for batch in batches for item in batch
        } | cached_numbers
        scheduled_characters = sum(
            item.character_count for batch in batches for item in batch
        )
        selected_count = len(scheduled_numbers)
        system_prompt = _read_prompt("issue_batch_system.txt")
        user_prompt = _read_prompt("issue_batch_user.txt")
        failed_batches = 0
        api_call_count = 0
        failure_reasons: list[str] = []
        saved_numbers = set(cached_numbers)
        unresolved: dict[int, BatchItem] = {}
        try:
            client = self.client or OpenAICompatibleClient(
                api_key,
                public.llm_base_url,
                public.llm_model,
            )
        except Exception as exc:
            failure_reasons.append(_error_code(exc))
            current_app.logger.warning("LLM client degraded: %s", _error_code(exc))
            run.ai_coverage_percent = 100 * analyzed / len(eligible) if eligible else 0
            success_percent = 100 * analyzed / selected_count if selected_count else 0
            self._update_semantic_scores(run, analysis_config, success_percent)
            self._replace_ai_findings(run)
            db.session.commit()
            return AIServiceResult(
                True,
                len(eligible),
                selected_count,
                analyzed,
                len(batches),
                0,
                max(len(eligible) - selected_count, 0),
                0,
                tuple(sorted(set(failure_reasons))),
                budget["profile"],
            )
        for batch in batches:
            try:
                api_call_count += 1
                result = client.analyze_issue_batch(
                    batch,
                    system_prompt,
                    user_prompt,
                    max_retries=budget["max_llm_retries"],
                )
                expected = {item.issue_number for item in batch}
                returned: set[int] = set()
                for item in result.items:
                    if item.issue_number not in expected:
                        continue
                    returned.add(item.issue_number)
                    issue = next(
                        value
                        for value in run.issues
                        if value.issue_number == item.issue_number
                    )
                    cache_key = _cache_key(issue, prompt_version, public.llm_model)
                    AICacheRepository.set(cache_key, item.model_dump())
                    self._save_item(run, item, cache_key, prompt_version, public.llm_model)
                    unresolved.pop(item.issue_number, None)
                    if item.issue_number not in saved_numbers:
                        saved_numbers.add(item.issue_number)
                        analyzed += 1
                for batch_item in batch:
                    if batch_item.issue_number not in returned:
                        unresolved[batch_item.issue_number] = batch_item
            except Exception as exc:
                failure_reasons.append(_error_code(exc))
                current_app.logger.warning("LLM batch degraded: %s", _error_code(exc))
                unresolved.update({item.issue_number: item for item in batch})

        retry_size = max(1, budget["llm_batch_issue_count"] // 2)
        remaining_batches = max(budget["ai_max_batches"] - api_call_count, 0)
        retry_items = list(unresolved.values())
        retry_batches = [
            retry_items[index : index + retry_size]
            for index in range(0, len(retry_items), retry_size)
        ][:remaining_batches]
        for batch in retry_batches:
            try:
                api_call_count += 1
                result = client.analyze_issue_batch(
                    batch,
                    system_prompt,
                    user_prompt,
                    max_retries=budget["max_llm_retries"],
                )
                expected = {item.issue_number for item in batch}
                for item in result.items:
                    if item.issue_number not in expected:
                        continue
                    issue = next(
                        value
                        for value in run.issues
                        if value.issue_number == item.issue_number
                    )
                    cache_key = _cache_key(issue, prompt_version, public.llm_model)
                    AICacheRepository.set(cache_key, item.model_dump())
                    self._save_item(run, item, cache_key, prompt_version, public.llm_model)
                    unresolved.pop(item.issue_number, None)
                    if item.issue_number not in saved_numbers:
                        saved_numbers.add(item.issue_number)
                        analyzed += 1
            except Exception as exc:
                failure_reasons.append(_error_code(exc))
                current_app.logger.warning("LLM retry batch degraded: %s", _error_code(exc))

        if unresolved:
            failed_batches += 1
            if not failure_reasons:
                failure_reasons.append("LLM_PARTIAL_RESULT")

        remaining_batches = max(budget["ai_max_batches"] - api_call_count, 0)
        duplicate_review_count = 0
        if remaining_batches:
            reviewed, duplicate_failures, duplicate_calls, duplicate_errors = (
                self._review_duplicates(
                    run,
                    client,
                    public.llm_model,
                    prompt_version,
                    {**analysis_config, **budget},
                    maximum_batches=remaining_batches,
                    maximum_characters=max(
                        budget["ai_max_total_characters"] - scheduled_characters,
                        0,
                    ),
                )
            )
            duplicate_review_count += reviewed
            failed_batches += duplicate_failures
            api_call_count += duplicate_calls
            failure_reasons.extend(duplicate_errors)

        run.ai_coverage_percent = 100 * analyzed / len(eligible) if eligible else 0
        success_percent = 100 * analyzed / selected_count if selected_count else 0
        self._update_semantic_scores(run, analysis_config, success_percent)
        self._replace_ai_findings(run)
        db.session.commit()
        return AIServiceResult(
            True,
            len(eligible),
            selected_count,
            analyzed,
            failed_batches,
            api_call_count,
            max(len(eligible) - selected_count, 0),
            duplicate_review_count,
            tuple(sorted(set(failure_reasons))),
            budget["profile"],
        )

    @staticmethod
    def _review_duplicates(
        run: AnalysisRun,
        client: OpenAICompatibleClient,
        model_name: str,
        prompt_version: str,
        config: dict,
        *,
        maximum_batches: int,
        maximum_characters: int,
    ) -> tuple[int, int, int, list[str]]:
        candidates = db.session.execute(
            db.select(DuplicateCandidate)
            .where(DuplicateCandidate.analysis_run_id == run.id)
            .order_by(DuplicateCandidate.similarity.desc())
            .limit(config["ai_duplicate_pair_limit"])
        ).scalars().all()
        if not candidates:
            return 0, 0, 0, []
        issue_map = {issue.issue_number: issue for issue in run.issues}
        pending: list[tuple[DuplicateCandidate, dict, str]] = []
        pending_characters = 0
        reviewed = 0
        for candidate in candidates:
            issue_a = issue_map.get(candidate.issue_a)
            issue_b = issue_map.get(candidate.issue_b)
            if issue_a is None or issue_b is None:
                continue
            pair = _duplicate_pair_payload(
                issue_a,
                issue_b,
                config["ai_duplicate_excerpt_characters"],
            )
            cache_key = _duplicate_cache_key(pair, prompt_version, model_name)
            cached = AICacheRepository.get(cache_key)
            if cached:
                _apply_duplicate_review(candidate, DuplicateReviewItem.model_validate(cached))
                reviewed += 1
            else:
                pair_characters = len(json.dumps(pair, ensure_ascii=False))
                if pending_characters + pair_characters > maximum_characters:
                    continue
                pending.append((candidate, pair, cache_key))
                pending_characters += pair_characters

        batch_size = int(config["ai_duplicate_batch_pair_count"])
        batches = [
            pending[index : index + batch_size]
            for index in range(0, len(pending), batch_size)
        ]
        batches = batches[:maximum_batches]
        system_prompt = _read_prompt("issue_batch_system.txt")
        user_prompt = _read_prompt("duplicate_batch_user.txt")
        failures = 0
        calls = 0
        errors: list[str] = []
        for batch in batches:
            try:
                calls += 1
                result = client.review_duplicate_batch(
                    [item[1] for item in batch],
                    system_prompt,
                    user_prompt,
                    max_retries=config["max_llm_retries"],
                )
                by_pair = {(item.issue_a, item.issue_b): item for item in result.pairs}
                for candidate, _payload, cache_key in batch:
                    item = by_pair.get((candidate.issue_a, candidate.issue_b))
                    if item is None:
                        continue
                    _apply_duplicate_review(candidate, item)
                    AICacheRepository.set(cache_key, item.model_dump())
                    reviewed += 1
            except Exception as exc:
                failures += 1
                errors.append(_error_code(exc))
                current_app.logger.warning(
                    "LLM duplicate review degraded: %s",
                    _error_code(exc),
                )
        return reviewed, failures, calls, errors

    @staticmethod
    def _update_semantic_scores(
        run: AnalysisRun,
        config: dict,
        success_percent: float,
    ) -> None:
        rows = db.session.execute(
            db.select(AIAnalysis).where(AIAnalysis.analysis_run_id == run.id)
        ).scalars().all()
        components: list[tuple[float, float]] = []
        quality = [
            row.semantic_quality_score
            for row in rows
            if row.semantic_quality_score is not None
        ]
        closure = [
            row.closure_quality_score
            for row in rows
            if row.closure_quality_score is not None
        ]
        if quality:
            components.append((sum(quality) / len(quality), 50))
        if closure:
            components.append((sum(closure) / len(closure), 30))

        reviewed_pairs = db.session.execute(
            db.select(DuplicateCandidate).where(
                DuplicateCandidate.analysis_run_id == run.id,
                DuplicateCandidate.llm_relation.is_not(None),
            )
        ).scalars().all()
        if reviewed_pairs:
            confirmed = {
                number
                for pair in reviewed_pairs
                if pair.llm_relation in {"duplicate", "strongly_related"}
                for number in (pair.issue_a, pair.issue_b)
            }
            duplicate_score = 100 * (1 - len(confirmed) / max(len(run.issues), 1))
            components.append((max(0.0, duplicate_score), 20))

        total_weight = sum(weight for _score, weight in components)
        run.ai_semantic_score = (
            round(sum(score * weight for score, weight in components) / total_weight, 2)
            if total_weight
            else None
        )
        confidence_values = [
            row.semantic_confidence * 100
            for row in rows
            if row.semantic_confidence is not None
        ] + [
            pair.llm_confidence * 100
            for pair in reviewed_pairs
            if pair.llm_confidence is not None
        ]
        run.ai_semantic_confidence = (
            round(sum(confidence_values) / len(confidence_values), 2)
            if confidence_values
            else None
        )
        minimum_coverage = config["ai_enhanced_score_min_coverage"]
        minimum_confidence = config["ai_enhanced_score_min_confidence"]
        ai_weight = config["ai_enhanced_score_weight"] / 100
        if (
            run.total_score is not None
            and run.ai_semantic_score is not None
            and success_percent >= minimum_coverage
            and (run.ai_semantic_confidence or 0) >= minimum_confidence
        ):
            run.enhanced_total_score = round(
                run.total_score * (1 - ai_weight) + run.ai_semantic_score * ai_weight,
                2,
            )
        else:
            run.enhanced_total_score = None

    @staticmethod
    def _replace_ai_findings(run: AnalysisRun) -> None:
        db.session.execute(
            db.delete(Finding).where(
                Finding.analysis_run_id == run.id,
                Finding.source_type == "AI",
            )
        )
        rows = db.session.execute(
            db.select(AIAnalysis).where(AIAnalysis.analysis_run_id == run.id)
        ).scalars().all()
        _add_ai_score_finding(
            run,
            rows,
            "semantic_quality_score",
            "D3",
            "AI3.1",
            "AI 语义信息质量需要改进",
        )
        _add_ai_score_finding(
            run,
            rows,
            "closure_quality_score",
            "D5",
            "AI5.1",
            "AI 判断的协作闭环质量需要改进",
        )
        duplicate_pairs = db.session.execute(
            db.select(DuplicateCandidate).where(
                DuplicateCandidate.analysis_run_id == run.id,
                DuplicateCandidate.llm_relation.in_(["duplicate", "strongly_related"]),
            )
        ).scalars().all()
        if duplicate_pairs:
            issue_numbers = {
                number for pair in duplicate_pairs for number in (pair.issue_a, pair.issue_b)
            }
            db.session.add(
                _ai_finding(
                    run,
                    "D6",
                    "AI6.1",
                    "AI 已确认高相似重复问题",
                    100 - min(100, 100 * len(issue_numbers) / max(len(run.issues), 1)),
                    len(issue_numbers),
                    len(run.issues),
                    "合并重复讨论，并把高频根因沉淀为 FAQ 或问题指南。",
                )
            )

    @staticmethod
    def _save_item(
        run: AnalysisRun,
        item: IssueAnalysisItem,
        input_hash: str,
        prompt_version: str,
        model_name: str,
    ) -> None:
        row = db.session.execute(
            db.select(AIAnalysis).where(
                AIAnalysis.analysis_run_id == run.id,
                AIAnalysis.issue_number == item.issue_number,
            )
        ).scalar_one_or_none()
        values = {
            "input_hash": input_hash,
            "prompt_version": prompt_version,
            "model_name": model_name,
            "category": item.category,
            "category_confidence": item.category_confidence,
            "completeness_json": item.missing_information,
            "quality_flags_json": item.quality_flags,
            "semantic_quality_score": item.semantic_quality_score,
            "closure_quality_score": item.closure_quality_score,
            "semantic_confidence": item.semantic_confidence,
            "knowledge_candidate": item.knowledge_candidate,
            "recommended_action": item.recommended_action,
            "evidence_json": item.evidence_quotes,
            "summary": item.semantic_summary,
            "explanation": item.reason,
            "status": "SUCCEEDED",
            "raw_response_hash": hashlib.sha256(
                json.dumps(item.model_dump(), sort_keys=True).encode("utf-8")
            ).hexdigest(),
        }
        if row is None:
            db.session.add(
                AIAnalysis(analysis_run_id=run.id, issue_number=item.issue_number, **values)
            )
        else:
            for key, value in values.items():
                setattr(row, key, value)
        db.session.commit()


def _select_issues(issues, labels_config: dict, maximum: int) -> list:
    """Round-robin sampling keeps the limited AI budget representative."""
    ordered = sorted(issues, key=lambda issue: issue.issue_number, reverse=True)
    buckets = [
        deque(issue for issue in ordered if is_low_information(issue.body_excerpt, 80)),
        deque(issue for issue in ordered if is_bug(issue, labels_config)),
        deque(issue for issue in ordered if issue.state == "open"),
        deque(issue for issue in ordered if issue.state == "closed"),
        deque(ordered),
    ]
    selected: list = []
    seen: set[int] = set()
    while len(selected) < maximum:
        made_progress = False
        for bucket in buckets:
            while bucket and bucket[0].issue_number in seen:
                bucket.popleft()
            if not bucket:
                continue
            issue = bucket.popleft()
            selected.append(issue)
            seen.add(issue.issue_number)
            made_progress = True
            if len(selected) >= maximum:
                break
        if not made_progress:
            break
    return selected


def _duplicate_pair_payload(issue_a, issue_b, excerpt_characters: int) -> dict:
    return {
        "issue_a": issue_a.issue_number,
        "issue_b": issue_b.issue_number,
        "title_a": issue_a.title[:300],
        "title_b": issue_b.title[:300],
        "body_a": issue_a.body_excerpt[:excerpt_characters],
        "body_b": issue_b.body_excerpt[:excerpt_characters],
    }


def _duplicate_cache_key(pair: dict, prompt_version: str, model_name: str) -> str:
    source = json.dumps(pair, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(
        f"{source}\n{prompt_version}\n{model_name}\nduplicate_batch".encode()
    ).hexdigest()


def _apply_duplicate_review(
    candidate: DuplicateCandidate,
    item: DuplicateReviewItem,
) -> None:
    candidate.llm_relation = item.relation
    candidate.llm_confidence = item.confidence
    candidate.llm_reason = item.reason


def _add_ai_score_finding(
    run: AnalysisRun,
    rows: list[AIAnalysis],
    field_name: str,
    dimension_code: str,
    metric_code: str,
    title: str,
) -> None:
    scored_rows = [row for row in rows if getattr(row, field_name) is not None]
    if not scored_rows:
        return
    average = sum(getattr(row, field_name) for row in scored_rows) / len(scored_rows)
    if average >= 75:
        return
    affected = [row for row in scored_rows if getattr(row, field_name) < 75]
    db.session.add(
        _ai_finding(
            run,
            dimension_code,
            metric_code,
            title,
            average,
            len(affected),
            len(scored_rows),
            "按 AI 给出的缺失信息、建议动作和证据摘录逐项处理，再重新检测。",
            [row.issue_number for row in affected],
        )
    )


def _ai_finding(
    run: AnalysisRun,
    dimension_code: str,
    metric_code: str,
    title: str,
    score: float,
    affected_count: int,
    sample_size: int,
    recommendation: str,
    issue_numbers: list[int] | None = None,
) -> Finding:
    severity = max(0.0, 100 - score)
    affected_rate = 100 * affected_count / max(sample_size, 1)
    priority = 0.6 * severity + 0.4 * affected_rate
    level = "HIGH" if priority >= 75 else "MEDIUM" if priority >= 45 else "LOW"
    evidence_query = db.select(EvidenceItem).where(EvidenceItem.analysis_run_id == run.id)
    if issue_numbers:
        evidence_query = evidence_query.where(EvidenceItem.issue_number.in_(issue_numbers))
    evidence_ids = [
        item.id
        for item in db.session.execute(evidence_query.limit(20)).scalars()
    ]
    return Finding(
        analysis_run_id=run.id,
        dimension_code=dimension_code,
        finding_code=f"LOW_{metric_code}",
        severity_score=round(severity, 2),
        priority_score=round(priority, 2),
        priority_level=level,
        title=title,
        summary=f"AI 语义评估得分为 {score:.2f}，低于 75 分参考线。",
        impact_text=f"影响 {affected_count}/{sample_size} 个 AI 已分析样本。",
        recommendation=recommendation,
        source_type="AI",
        metric_code=metric_code,
        affected_count=affected_count,
        sample_size=sample_size,
        evidence_ids_json=evidence_ids,
        status="OPEN",
    )


def _cache_key(issue, prompt_version: str, model_name: str) -> str:
    normalized = " ".join(f"{issue.title}\n{issue.body_excerpt}".split())
    metadata = json.dumps(
        {
            "state": issue.state,
            "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
            "labels": issue.labels_json,
            "linked_pull_requests": issue.linked_pr_numbers_json,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    source = f"{normalized}\n{metadata}\n{prompt_version}\n{model_name}\nissue_batch"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _error_code(error: Exception) -> str:
    code = str(getattr(error, "code", type(error).__name__))
    cause = error.__cause__
    return f"{code}/{type(cause).__name__}" if cause is not None else code


def _read_prompt(name: str) -> str:
    path = Path(__file__).parent.parent / "ai" / "prompts" / name
    return path.read_text(encoding="utf-8")
