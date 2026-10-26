import hashlib
from collections import defaultdict

from issuedoctor.extensions import db
from issuedoctor.github.schemas import CommentData, IssueData, LabelData, PullRequestData
from issuedoctor.models import EvidenceItem, IssueSnapshot, PullRequestSnapshot

MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
BODY_EXCERPT_LIMIT = 6000
EVIDENCE_EXCERPT_LIMIT = 1000


def _excerpt(value: str | None, limit: int = BODY_EXCERPT_LIMIT) -> str:
    return (value or "")[:limit]


def _hash(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _labels(values: list[LabelData | str]) -> list[dict | str]:
    return [value.model_dump() if isinstance(value, LabelData) else value for value in values]


class SnapshotRepository:
    @staticmethod
    def replace(
        run_id: str,
        issues: list[IssueData],
        pull_requests: list[PullRequestData],
        comments: list[CommentData],
        *,
        issue_links: dict[int, list[int]] | None = None,
        pr_links: dict[int, list[int]] | None = None,
        link_methods: dict[int, list[dict]] | None = None,
    ) -> None:
        issue_links = issue_links or {}
        pr_links = pr_links or {}
        link_methods = link_methods or {}
        db.session.execute(db.delete(IssueSnapshot).where(IssueSnapshot.analysis_run_id == run_id))
        db.session.execute(
            db.delete(PullRequestSnapshot).where(PullRequestSnapshot.analysis_run_id == run_id)
        )
        db.session.execute(db.delete(EvidenceItem).where(EvidenceItem.analysis_run_id == run_id))

        comments_by_issue: dict[int, list[CommentData]] = defaultdict(list)
        for comment in comments:
            comments_by_issue[comment.issue_number].append(comment)

        for issue in issues:
            maintainer_comments = sorted(
                (
                    comment
                    for comment in comments_by_issue[issue.number]
                    if comment.author_association in MAINTAINER_ASSOCIATIONS
                    and comment.created_at >= issue.created_at
                ),
                key=lambda comment: comment.created_at,
            )
            first_response = maintainer_comments[0] if maintainer_comments else None
            first_hours = (
                (first_response.created_at - issue.created_at).total_seconds() / 3600
                if first_response
                else None
            )
            db.session.add(
                IssueSnapshot(
                    analysis_run_id=run_id,
                    issue_number=issue.number,
                    title=issue.title,
                    body_excerpt=_excerpt(issue.body),
                    body_hash=_hash(issue.body),
                    state=issue.state,
                    html_url=issue.html_url,
                    author_login=issue.user.login,
                    author_association=issue.author_association,
                    created_at=issue.created_at,
                    updated_at=issue.updated_at,
                    closed_at=issue.closed_at,
                    comments_count=issue.comments,
                    labels_json=_labels(issue.labels),
                    first_maintainer_response_at=(
                        first_response.created_at if first_response else None
                    ),
                    first_maintainer_response_hours=first_hours,
                    maintainer_response_found=bool(first_response),
                    last_maintainer_activity_at=(
                        maintainer_comments[-1].created_at if maintainer_comments else None
                    ),
                    linked_pr_numbers_json=issue_links.get(issue.number, []),
                )
            )
            for comment in maintainer_comments:
                db.session.add(
                    EvidenceItem(
                        analysis_run_id=run_id,
                        issue_number=issue.number,
                        evidence_type="MAINTAINER_COMMENT",
                        excerpt=_excerpt(comment.body, EVIDENCE_EXCERPT_LIMIT),
                        source_url=comment.html_url,
                        actor_login=comment.user.login,
                        actor_association=comment.author_association,
                        happened_at=comment.created_at,
                        metadata_json={},
                    )
                )

        for pull_request in pull_requests:
            db.session.add(
                PullRequestSnapshot(
                    analysis_run_id=run_id,
                    pr_number=pull_request.number,
                    title=pull_request.title,
                    body_excerpt=_excerpt(pull_request.body),
                    body_hash=_hash(pull_request.body),
                    state=pull_request.state,
                    html_url=pull_request.html_url,
                    author_login=pull_request.user.login,
                    author_association=pull_request.author_association,
                    created_at=pull_request.created_at,
                    updated_at=pull_request.updated_at,
                    closed_at=pull_request.closed_at,
                    merged_at=pull_request.merged_at,
                    labels_json=_labels(pull_request.labels),
                    linked_issue_numbers_json=pr_links.get(pull_request.number, []),
                    link_method_json=link_methods.get(pull_request.number, []),
                )
            )
        db.session.commit()
