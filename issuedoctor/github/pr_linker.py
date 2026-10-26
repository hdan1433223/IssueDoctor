import re
from dataclasses import dataclass

CLOSING_REFERENCE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)"
)
PLAIN_REFERENCE = re.compile(r"(?<![\w/])#(\d+)\b")
PULL_URL = re.compile(r"https://github\.com/[^/]+/[^/]+/pull/(\d+)")


@dataclass(frozen=True)
class LinkResult:
    issue_to_prs: dict[int, list[int]]
    pr_to_issues: dict[int, list[int]]
    methods_by_pr: dict[int, list[dict]]


def link_issues_and_pull_requests(issues: list, pull_requests: list) -> LinkResult:
    issue_numbers = {issue.number for issue in issues}
    issue_to_prs: dict[int, set[int]] = {number: set() for number in issue_numbers}
    pr_to_issues: dict[int, set[int]] = {pr.number: set() for pr in pull_requests}
    methods: dict[int, list[dict]] = {pr.number: [] for pr in pull_requests}

    for pr in pull_requests:
        body = pr.body or ""
        closing = {int(value) for value in CLOSING_REFERENCE.findall(body)} & issue_numbers
        plain = ({int(value) for value in PLAIN_REFERENCE.findall(body)} & issue_numbers) - closing
        for issue_number in sorted(closing | plain):
            method = "PR_CLOSING_KEYWORD" if issue_number in closing else "PR_BODY_REFERENCE"
            confidence = 1.0 if issue_number in closing else 0.7
            issue_to_prs[issue_number].add(pr.number)
            pr_to_issues[pr.number].add(issue_number)
            methods[pr.number].append(
                {"issue_number": issue_number, "link_method": method, "confidence": confidence}
            )

    pr_numbers = {pr.number for pr in pull_requests}
    for issue in issues:
        referenced = {int(value) for value in PULL_URL.findall(issue.body or "")} & pr_numbers
        for pr_number in sorted(referenced):
            issue_to_prs[issue.number].add(pr_number)
            pr_to_issues[pr_number].add(issue.number)
            methods[pr_number].append(
                {
                    "issue_number": issue.number,
                    "link_method": "ISSUE_BODY_PR_URL",
                    "confidence": 0.8,
                }
            )

    return LinkResult(
        issue_to_prs={key: sorted(values) for key, values in issue_to_prs.items()},
        pr_to_issues={key: sorted(values) for key, values in pr_to_issues.items()},
        methods_by_pr=methods,
    )
