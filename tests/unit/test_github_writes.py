from types import SimpleNamespace

import httpx
import pytest

from issuedoctor.errors import IssueDoctorError
from issuedoctor.github.branch_pr_writer import BranchPullRequestWriter
from issuedoctor.github.label_writer import LabelDeleteConfirmation, LabelWriter
from issuedoctor.github.write_client import GitHubWriteClient


class FakeGitHubWriter:
    def __init__(self):
        self.calls = []

    def get_repository(self, full_name):
        self.calls.append(("get_repository", full_name))
        return {"full_name": full_name, "default_branch": "main"}

    def get_reference(self, full_name, branch):
        self.calls.append(("get_reference", branch))
        return {"object": {"sha": "parent-sha"}}

    def get_file(self, full_name, path, reference):
        self.calls.append(("get_file", path, reference))
        return ""

    def get_commit(self, full_name, sha):
        self.calls.append(("get_commit", sha))
        return {"tree": {"sha": "base-tree"}}

    def create_reference(self, full_name, branch, sha):
        self.calls.append(("create_reference", branch, sha))
        return {}

    def create_tree(self, full_name, base_tree, entries):
        self.calls.append(("create_tree", base_tree, entries))
        return {"sha": "tree-sha"}

    def create_commit(self, full_name, message, tree_sha, parent_sha):
        self.calls.append(("create_commit", tree_sha, parent_sha))
        return {"sha": "commit-sha"}

    def update_reference(self, full_name, branch, sha):
        self.calls.append(("update_reference", branch, sha))
        return {}

    def create_pull_request(self, full_name, title, body, head, base):
        self.calls.append(("create_pull_request", head, base))
        return {"number": 9, "html_url": "https://github.com/example/project/pull/9"}

    def label_issue_count(self, full_name, name):
        self.calls.append(("label_issue_count", name))
        return 12

    def delete_label(self, full_name, name):
        self.calls.append(("delete_label", name))


def test_branch_writer_never_updates_default_branch():
    client = FakeGitHubWriter()
    package = SimpleNamespace(
        files_json={
            "CONTRIBUTING.md": {
                "content": "# Contributing\n\nGuidance\n",
                "original_content": "",
            }
        }
    )

    result = BranchPullRequestWriter(client).create(
        "example/project",
        package,
        confirmed=True,
    )

    updated_branches = [call[1] for call in client.calls if call[0] == "update_reference"]
    assert updated_branches == [result["branch"]]
    assert result["branch"].startswith("issuedoctor/governance-")
    assert "main" not in updated_branches
    assert ("create_pull_request", result["branch"], "main") in client.calls


def test_branch_writer_requires_explicit_confirmation():
    with pytest.raises(IssueDoctorError) as error:
        BranchPullRequestWriter(FakeGitHubWriter()).create(
            "example/project",
            SimpleNamespace(files_json={}),
            confirmed=False,
        )
    assert error.value.code == "WRITE_CONFIRMATION_REQUIRED"


@pytest.mark.parametrize(
    "confirmation",
    [
        LabelDeleteConfirmation(False, "example/project", True),
        LabelDeleteConfirmation(True, "wrong/project", True),
        LabelDeleteConfirmation(True, "example/project", False),
    ],
)
def test_label_delete_confirmation_cannot_be_bypassed(confirmation):
    client = FakeGitHubWriter()
    with pytest.raises(IssueDoctorError) as error:
        LabelWriter(client).delete("example/project", "obsolete", confirmation)

    assert error.value.code == "LABEL_DELETE_CONFIRMATION_FAILED"
    assert not client.calls


def test_label_delete_rechecks_repository_and_reports_impact():
    client = FakeGitHubWriter()
    result = LabelWriter(client).delete(
        "example/project",
        "obsolete",
        LabelDeleteConfirmation(True, "example/project", True),
    )

    assert result == {"label": "obsolete", "affected_issue_count": 12, "deleted": True}
    assert client.calls == [
        ("get_repository", "example/project"),
        ("label_issue_count", "obsolete"),
        ("delete_label", "obsolete"),
    ]


def test_write_client_fails_safely_without_permission():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    with GitHubWriteClient("super-secret", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IssueDoctorError) as error:
            client.get_repository("example/project")

    assert error.value.code == "GITHUB_PERMISSION_INSUFFICIENT"
    assert "super-secret" not in error.value.message
