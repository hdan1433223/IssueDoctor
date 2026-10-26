import math
from urllib.parse import urlsplit


def effective_ai_budget(
    config: dict,
    base_url: str,
    requested_issues: int | None = None,
) -> dict:
    budget = {
        "ai_max_issues": int(config["ai_max_issues"]),
        "ai_max_total_characters": int(config["ai_max_total_characters"]),
        "ai_max_batches": int(config["ai_max_batches"]),
        "llm_batch_issue_count": int(config["llm_batch_issue_count"]),
        "llm_batch_total_chars": int(config["llm_batch_total_chars"]),
        "issue_body_max_chars": int(config["issue_body_max_chars"]),
        "ai_duplicate_pair_limit": int(config["ai_duplicate_pair_limit"]),
        "ai_duplicate_batch_pair_count": int(config["ai_duplicate_batch_pair_count"]),
        "ai_duplicate_excerpt_characters": int(
            config["ai_duplicate_excerpt_characters"]
        ),
        "max_llm_retries": int(config["max_llm_retries"]),
        "profile": "default",
        "user_max_issues": int(config["ai_max_issues"]),
        "user_max_batches": int(config["ai_max_batches"]),
    }
    if requested_issues is not None:
        budget["ai_max_issues"] = max(
            1,
            min(int(requested_issues), int(config["ai_max_issues"])),
        )
    if (urlsplit(base_url).hostname or "").lower() == "api.groq.com":
        issue_count = budget["ai_max_issues"] if requested_issues is not None else min(
            budget["ai_max_issues"],
            30,
        )
        limits = {
            "ai_max_issues": issue_count,
            "ai_max_total_characters": min(
                int(config["ai_max_total_characters"]),
                max(10_000, issue_count * 1_500),
            ),
            "ai_max_batches": min(
                int(config["ai_max_batches"]),
                math.ceil(issue_count / 8) + 1,
            ),
            "llm_batch_issue_count": 8,
            "llm_batch_total_chars": 10_000,
            "issue_body_max_chars": 800,
            "ai_duplicate_pair_limit": 3,
            "ai_duplicate_batch_pair_count": 3,
            "ai_duplicate_excerpt_characters": 300,
            "max_llm_retries": 1,
        }
        for key, limit in limits.items():
            budget[key] = limit
        budget["profile"] = "groq-free-safe"
    return budget
