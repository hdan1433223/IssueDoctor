from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from flask import current_app
from sqlalchemy import func

from issuedoctor.ai.client import OpenAICompatibleClient
from issuedoctor.errors import IssueDoctorError
from issuedoctor.extensions import db
from issuedoctor.models import (
    AIAnalysis,
    AnalysisRun,
    DimensionScore,
    DuplicateCandidate,
    EvidenceItem,
    Finding,
    GovernancePackage,
    IssueSnapshot,
    MetricResult,
)
from issuedoctor.models.assistant import AssistantKnowledgeBase, AssistantKnowledgeChunk
from issuedoctor.rag import INDEX_VERSION, AssistantKnowledgeBuilder, retrieve_chunks
from issuedoctor.rag.retrieval import build_context, embed_text
from issuedoctor.security.secrets import LLM_API_KEY
from issuedoctor.services.settings_service import SettingsService


class AssistantService:
    def __init__(self, client: OpenAICompatibleClient | None = None) -> None:
        self.client = client

    def ensure_index(self, run: AnalysisRun, *, force: bool = False) -> AssistantKnowledgeBase:
        fingerprint = self._source_fingerprint(run)
        knowledge = db.session.get(AssistantKnowledgeBase, run.id)
        if (
            not force
            and knowledge is not None
            and knowledge.index_version == INDEX_VERSION
            and knowledge.source_fingerprint == fingerprint
        ):
            return knowledge
        return self.rebuild(run, fingerprint=fingerprint)

    def rebuild(
        self,
        run: AnalysisRun,
        *,
        fingerprint: str | None = None,
    ) -> AssistantKnowledgeBase:
        chunks = AssistantKnowledgeBuilder().build(run)
        for chunk in chunks:
            chunk.analysis_run_id = run.id
            chunk.vector_json = embed_text(f"{chunk.title}\n{chunk.content}")
        db.session.execute(
            db.delete(AssistantKnowledgeChunk).where(
                AssistantKnowledgeChunk.analysis_run_id == run.id
            )
        )
        knowledge = db.session.get(AssistantKnowledgeBase, run.id)
        if knowledge is None:
            knowledge = AssistantKnowledgeBase(
                analysis_run_id=run.id,
                index_version=INDEX_VERSION,
                source_fingerprint=fingerprint or self._source_fingerprint(run),
                chunk_count=len(chunks),
            )
            db.session.add(knowledge)
        else:
            knowledge.index_version = INDEX_VERSION
            knowledge.source_fingerprint = fingerprint or self._source_fingerprint(run)
            knowledge.chunk_count = len(chunks)
        db.session.add_all(chunks)
        db.session.commit()
        return knowledge

    def answer(
        self,
        run: AnalysisRun,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict:
        normalised_question = " ".join(str(question or "").split())
        if len(normalised_question) < 2:
            raise IssueDoctorError(
                "ASSISTANT_QUESTION_TOO_SHORT",
                "请输入至少两个字符的问题",
                status_code=422,
            )
        if len(normalised_question) > 2_000:
            raise IssueDoctorError(
                "ASSISTANT_QUESTION_TOO_LONG",
                "问题不能超过 2000 个字符",
                status_code=422,
            )
        if run.status not in {"SUCCEEDED", "PARTIAL"}:
            raise IssueDoctorError(
                "ASSISTANT_REPORT_NOT_READY",
                "本次审计尚未成功完成，暂时不能使用报告助手",
                status_code=409,
            )

        safe_history = self._normalise_history(history or [])
        retrieval_question = normalised_question
        previous_user = next(
            (
                item["content"]
                for item in reversed(safe_history)
                if item["role"] == "user"
            ),
            "",
        )
        if previous_user and (
            len(normalised_question) <= 12
            or normalised_question.startswith(("那", "还有", "继续", "再", "它"))
        ):
            retrieval_question = f"{previous_user}\n{normalised_question}"

        knowledge = self.ensure_index(run)
        chunks = db.session.execute(
            db.select(AssistantKnowledgeChunk).where(
                AssistantKnowledgeChunk.analysis_run_id == run.id
            )
        ).scalars().all()
        results = retrieve_chunks(retrieval_question, list(chunks), limit=4)
        if not results:
            return {
                "answer": (
                    "本次报告的知识库中没有检索到能够回答该问题的依据。"
                    "请换一种说法，或直接查看报告总览、维度详情和证据页。"
                ),
                "key_points": [],
                "limitations": "未找到相关报告片段。",
                "mode": "extractive",
                "sources": [],
                "indexed_at": knowledge.indexed_at.isoformat(),
                "scope": "本次报告",
            }

        client = self.client
        llm_configured = client is not None
        if client is None:
            settings = SettingsService()
            api_key = settings.secret_store.get(LLM_API_KEY)
            public = settings.get_public()
            if api_key and public.llm_model:
                client = OpenAICompatibleClient(
                    api_key,
                    public.llm_base_url,
                    public.llm_model,
                    timeout_seconds=30,
                )
                llm_configured = True
        llm_failure_code = None
        if client is not None:
            try:
                answer = client.answer_report_question(
                    normalised_question,
                    build_context(results),
                    safe_history,
                    _read_prompt("assistant_system.txt"),
                    max_retries=1,
                )
                sources = self._sources(results)
                cited = set(answer.source_ids)
                if cited:
                    sources = [
                        item
                        for item in sources
                        if item["id"] in cited or item["label"] in cited
                    ] or sources[:4]
                return {
                    "answer": answer.answer,
                    "key_points": answer.key_points[:8],
                    "limitations": answer.limitations,
                    "mode": "enhanced",
                    "sources": sources,
                    "indexed_at": knowledge.indexed_at.isoformat(),
                    "scope": "本次报告",
                }
            except Exception as exc:
                llm_failure_code = _llm_error_code(exc)
                current_app.logger.warning(
                    "Assistant LLM degraded to extractive answer for run %s (%s)",
                    run.id,
                    llm_failure_code,
                )

        return self._extractive_answer(
            normalised_question,
            results,
            knowledge,
            run,
            llm_configured=llm_configured,
            llm_failure_code=llm_failure_code,
        )

    @staticmethod
    def _normalise_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
        result = []
        for item in history[-4:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = str(item.get("content", "")).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            result.append({"role": role, "content": content[:500]})
        return result

    @staticmethod
    def _sources(results) -> list[dict]:
        return [
            {
                "id": item.source_id,
                "label": f"K{index}",
                "title": item.title,
                "source_type": item.source_type,
                "page_url": item.page_url,
                "github_url": item.github_url,
                "excerpt": _clip(item.content, 220),
                "score": item.score,
            }
            for index, item in enumerate(results, start=1)
        ]

    @staticmethod
    def _extractive_answer(
        question,
        results,
        knowledge,
        run: AnalysisRun,
        *,
        llm_configured: bool,
        llm_failure_code: str | None,
    ) -> dict:
        findings = [
            (index, item)
            for index, item in enumerate(results, start=1)
            if item.source_type == "finding"
        ]
        action_question = any(
            word in question
            for word in ("怎么解决", "如何解决", "怎么改", "如何改", "下一步", "行动")
        )
        selected = findings[:5] if action_question else findings[:3]
        points = [
            _finding_point(index, item, action_question=action_question)
            for index, item in selected
        ]
        if not points:
            points = [
                f"K{index}：{_clip(' '.join(item.content.split()), 260)}"
                for index, item in enumerate(results[:3], start=1)
            ]
        if action_question and points:
            answer = (
                "建议按优先级从以下五步处理。"
                "优先修复影响样本多、优先级高的规则问题，再补充模板和分类基础设施。"
            )
        elif points:
            answer = "本次报告最需要优先关注的是以下问题。"
        else:
            answer = "当前检索结果中没有可总结的具体问题，请打开来源查看完整报告。"

        limitations = "回答仅基于本次报告的已采集样本和规则结果。"
        llm_error = None
        if llm_failure_code:
            llm_error = {
                "code": llm_failure_code,
                "message": _llm_failure_message(llm_failure_code),
            }
            limitations = (
                "检测到已保存的 LLM 配置，但本次模型调用失败。"
                f"{_llm_failure_message(llm_failure_code)}"
                "当前先返回确定性规则摘要；修复连接后会自动使用 LLM 生成综合回答。"
            )
        elif not llm_configured:
            limitations = (
                "当前没有可用的 LLM 配置，已返回规则驱动的摘要。"
                "在设置页配置 API Key、Base URL 和模型名后会生成综合解释。"
            )
        if run.status == "PARTIAL":
            limitations += " 本次 AI 或数据采集存在部分降级，结论需要结合报告限制阅读。"
        return {
            "answer": answer,
            "key_points": points,
            "limitations": limitations,
            "mode": "extractive",
            "sources": AssistantService._sources(results),
            "llm_error": llm_error,
            "indexed_at": knowledge.indexed_at.isoformat(),
            "scope": "本次报告",
        }

    @staticmethod
    def _source_fingerprint(run: AnalysisRun) -> str:
        models = (
            IssueSnapshot,
            MetricResult,
            DimensionScore,
            Finding,
            AIAnalysis,
            EvidenceItem,
            DuplicateCandidate,
        )
        counts: dict[str, tuple[int, int | None]] = {}
        for model in models:
            count, maximum = db.session.execute(
                db.select(func.count(model.id), func.max(model.id)).where(
                    model.analysis_run_id == run.id
                )
            ).one()
            counts[model.__tablename__] = (
                int(count or 0),
                int(maximum) if maximum is not None else None,
            )
        package = db.session.execute(
            db.select(GovernancePackage).where(GovernancePackage.analysis_run_id == run.id)
        ).scalar_one_or_none()
        payload = {
            "index_version": INDEX_VERSION,
            "run_id": run.id,
            "status": run.status,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "total_score": run.total_score,
            "confidence": run.confidence_score,
            "ai_coverage": run.ai_coverage_percent,
            "analysis_config": run.analysis_config_json,
            "counts": counts,
            "governance": (
                [package.id, package.updated_at.isoformat()]
                if package is not None
                else None
            ),
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _read_prompt(name: str) -> str:
    path = Path(__file__).parent.parent / "ai" / "prompts" / name
    return path.read_text(encoding="utf-8")


def _clip(value: str, maximum: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= maximum else text[: maximum - 1].rstrip() + "…"


def _finding_point(
    index: int,
    item,
    *,
    action_question: bool,
) -> str:
    fields = {}
    for line in item.content.splitlines():
        if "：" in line:
            key, value = line.split("：", 1)
            fields[key] = value.strip()
    metric = fields.get("指标", item.title)
    metric_code = _metric_code(metric)
    if action_question:
        action = _metric_action(metric_code)
        impact = fields.get("影响", "")
        return f"K{index} · {metric}：{action}（{impact}）"
    summary = fields.get("摘要", item.content)
    return f"K{index} · {fields.get('优先级', '')} · {metric}：{summary}"


def _metric_code(value: str) -> str:
    match = re.match(r"(M\d\.\d|AI\d\.\d)", value)
    return match.group(1) if match else ""


def _metric_action(metric_code: str) -> str:
    actions = {
        "M1.2": "建立每周未响应清单，先处理等待时间最长且影响用户最多的问题。",
        "M1.3": "为长期无维护活动的 Issue 安排一次回收，逐项回复、关闭或重新标记。",
        "M2.2": "优先清理超过 90 天的开放 Issue，明确继续跟踪、等待信息或关闭。",
        "M2.3": "控制新增节奏并提高有效关闭率，避免关闭与新增长期失衡。",
        "M3.1": "启用 Bug Issue Form，强制收集版本、环境、复现步骤、预期和实际结果。",
        "M3.3": "为 Bug、功能请求和使用问题分别提供结构化模板。",
        "M4.1": "在 triage 阶段为每个新 Issue 至少添加一个状态或类型标签。",
        "M4.2": "统一 `type: bug`、`type: feature`、`type: question`、`type: docs` 标签。",
        "M4.3": "合并同义标签，保留一套稳定的标签命名和描述。",
        "M4.4": "为所有正在使用的标签补充用途说明。",
        "M5.1": "关闭 Issue 时写明 fixed、duplicate、invalid 或 wontfix，并关联对应 PR。",
        "M5.2": "补齐 Issue 与解决 PR 的关联，在合并后同步更新 Issue 状态。",
        "M5.3": "禁止无说明关闭；将关闭原因纳入 triage 模板和日常检查。",
        "M5.4": "缩短从 Issue 到关联 PR 合并的等待时间，优先处理阻塞时间最长的问题。",
        "M6.1": "复核高相似候选，合并重复讨论并链接到现有 Issue。",
        "M6.2": "把高频重复主题整理为 FAQ 或故障排查指南。",
        "M6.3": "补充 Issue Forms、贡献指南、Issue 模板配置和 triage 文档。",
    }
    return actions.get(
        metric_code,
        "打开对应指标和原始证据，确认影响样本后制定整改动作。",
    )


def _llm_error_code(error: Exception) -> str:
    current = error
    for _ in range(6):
        if current is None:
            break
        status = getattr(current, "status_code", None)
        code = getattr(current, "code", None)
        name = type(current).__name__.lower()
        if status in {401, 403}:
            return "LLM_AUTH_FAILED"
        if status == 429:
            return "LLM_RATE_LIMITED"
        if "timeout" in name:
            return "LLM_TIMEOUT"
        if "connection" in name:
            return "LLM_CONNECTION_FAILED"
        if code in {"LLM_INVALID_JSON", "LLM_RETRY_EXHAUSTED"}:
            return "LLM_INVALID_JSON"
        current = getattr(current, "__cause__", None)
    return "ASSISTANT_LLM_FAILED"


def _llm_failure_message(code: str) -> str:
    messages = {
        "LLM_AUTH_FAILED": "API Key 无效、已过期，或与当前 Base URL 不匹配。",
        "LLM_RATE_LIMITED": "模型服务当前限流，请稍后重试或降低请求频率。",
        "LLM_TIMEOUT": "模型服务响应超时，请检查网络或更换可用模型。",
        "LLM_CONNECTION_FAILED": "无法连接模型服务，请检查 Base URL 和网络。",
        "LLM_INVALID_JSON": "模型返回的字段结构不符合问答格式，系统未能通过校验。",
    }
    return messages.get(code, "请到设置页测试连接并检查模型配置。")
