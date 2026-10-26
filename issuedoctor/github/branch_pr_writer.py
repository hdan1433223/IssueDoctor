from datetime import datetime

from issuedoctor.compat import UTC
from issuedoctor.errors import IssueDoctorError
from issuedoctor.github.write_client import GitHubWriteClient
from issuedoctor.models import GovernancePackage
from issuedoctor.security.governance_paths import validate_governance_path
from issuedoctor.services.governance_service import GovernanceService


class BranchPullRequestWriter:
    def __init__(self, client: GitHubWriteClient) -> None:
        self.client = client

    def create(self, full_name: str, package: GovernancePackage, *, confirmed: bool) -> dict:
        if not confirmed:
            raise IssueDoctorError("WRITE_CONFIRMATION_REQUIRED", "创建治理 PR 前必须确认 Diff")
        repository = self.client.get_repository(full_name)
        default_branch = repository["default_branch"]
        reference = self.client.get_reference(full_name, default_branch)
        parent_sha = reference["object"]["sha"]
        commit = self.client.get_commit(full_name, parent_sha)
        base_tree = commit["tree"]["sha"]
        entries = []
        for path, data in package.files_json.items():
            normalized = validate_governance_path(path)
            content = GovernanceService.validate_file(normalized, data["content"])
            current_content = self.client.get_file(full_name, normalized, default_branch)
            if current_content.replace("\r\n", "\n") != data.get("original_content", ""):
                raise IssueDoctorError(
                    "GITHUB_WRITE_CONFLICT",
                    f"{normalized} 自预览后已发生变化，请重新生成 Diff",
                    status_code=409,
                )
            entries.append(
                {"path": normalized, "mode": "100644", "type": "blob", "content": content}
            )
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        branch = f"issuedoctor/governance-{timestamp}"
        self.client.create_reference(full_name, branch, parent_sha)
        tree = self.client.create_tree(full_name, base_tree, entries)
        new_commit = self.client.create_commit(
            full_name,
            "chore: improve issue workflow with IssueDoctor",
            tree["sha"],
            parent_sha,
        )
        self.client.update_reference(full_name, branch, new_commit["sha"])
        pull_request = self.client.create_pull_request(
            full_name,
            "chore: improve issue workflow with IssueDoctor",
            _pull_request_body(package),
            branch,
            default_branch,
        )
        return {
            "branch": branch,
            "pull_request_number": pull_request["number"],
            "pull_request_url": pull_request["html_url"],
            "default_branch": default_branch,
        }


def _pull_request_body(package: GovernancePackage) -> str:
    paths = "\n".join(f"- `{path}`" for path in package.files_json)
    return f"""## IssueDoctor 治理建议

本次变更针对 Issue 信息质量、分类和协作闭环生成。

### 修改文件

{paths}

### 预期改进

- 提升 Bug 报告可复现性
- 统一 Issue 分类与维护者响应流程
- 让关闭原因和解决证据更清晰

> 此 Pull Request 由 IssueDoctor 自动生成，必须由仓库维护者审核后再合并。
"""
