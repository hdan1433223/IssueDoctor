from issuedoctor.exports.schemas import ReportDTO


def export_markdown(report: ReportDTO) -> bytes:
    repository = report.repository
    scores = report.scores
    lines = [
        f"# IssueDoctor 报告：{repository['full_name']}",
        "",
        f"- 分析状态：{report.analysis_metadata['status']}",
        f"- 分析模式：{report.analysis_metadata['mode']}",
        f"- 综合健康度：{_score(scores['total'])}",
        f"- AI 语义评分：{_score(scores.get('ai_semantic'))}",
        f"- AI 增强综合分：{_score(scores.get('enhanced_total'))}",
        f"- 数据置信度：{_score(scores['confidence'])}",
        f"- AI 覆盖率：{scores['ai_coverage_percent']:.1f}%",
        f"- AI 请求成功率：{scores.get('ai_success_percent', 0):.1f}%",
        "",
        "## 六维评分",
        "",
        "| 维度 | 分数 | 名义权重 | 有效权重 |",
        "|---|---:|---:|---:|",
    ]
    for item in scores["dimensions"]:
        lines.append(
            "| {code} | {score} | {nominal:.1f}% | {effective:.1f}% |".format(
                code=item["code"],
                score=_score(item["score"]),
                nominal=item["nominal_weight"],
                effective=item["effective_weight"],
            )
        )
    lines.extend(["", "## 主要 Findings", ""])
    for finding in report.findings:
        lines.extend(
            [
                f"### [{finding['priority_level']}] {finding['title']}",
                "",
                finding["summary"],
                "",
                f"- 影响：{finding['impact_text']}",
                f"- 建议：{finding['recommendation']}",
                "",
            ]
        )
    lines.extend(["## 数据限制", ""])
    if report.analysis_metadata["is_truncated"]:
        lines.append("本次分析达到配置数量上限，结果基于截断后的数据快照。")
    else:
        lines.append("本次分析未命中配置数量上限。")
    lines.extend(["", "---", "由 IssueDoctor 规则评分引擎生成；AI 增强结果单独标注。"])
    return ("\n".join(lines) + "\n").encode("utf-8")


def _score(value) -> str:
    return "N/A" if value is None else f"{value:.1f}"
