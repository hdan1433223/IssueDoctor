import json

from issuedoctor.ai.batching import BatchItem


def build_issue_messages(
    system_prompt: str,
    user_template: str,
    items: list[BatchItem],
) -> list[dict]:
    data = [
        {
            "issue_number": item.issue_number,
            "title": item.title,
            "body": item.body,
            "metadata": item.metadata,
        }
        for item in items
    ]
    serialized = json.dumps(data, ensure_ascii=False)
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": user_template.replace("{{ISSUES_JSON}}", serialized),
        },
    ]


def build_duplicate_messages(
    system_prompt: str,
    user_template: str,
    pairs: list[dict],
) -> list[dict]:
    serialized = json.dumps(pairs, ensure_ascii=False)
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": user_template.replace("{{PAIRS_JSON}}", serialized),
        },
    ]
