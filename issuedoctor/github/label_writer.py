from dataclasses import dataclass

from issuedoctor.errors import IssueDoctorError
from issuedoctor.github.write_client import GitHubWriteClient


@dataclass(frozen=True)
class LabelDeleteConfirmation:
    acknowledged_impact: bool
    repository_full_name: str
    confirm_delete: bool


class LabelWriter:
    def __init__(self, client: GitHubWriteClient) -> None:
        self.client = client

    def apply(self, full_name: str, plan: list[dict], *, confirmed: bool) -> list[dict]:
        if not confirmed:
            raise IssueDoctorError("WRITE_CONFIRMATION_REQUIRED", "应用 Label 方案前必须确认")
        repository = self.client.get_repository(full_name)
        if repository.get("full_name", "").lower() != full_name.lower():
            raise IssueDoctorError("GITHUB_WRITE_CONFLICT", "仓库状态校验失败", status_code=409)
        current = {label["name"].lower(): label for label in self.client.list_labels(full_name)}
        results = []
        for item in plan:
            action = item.get("action")
            payload = {
                "name": item["name"],
                "color": item["color"],
                "description": item.get("description", ""),
            }
            if action == "create" and item["name"].lower() not in current:
                results.append(self.client.create_label(full_name, payload))
            elif action in {"update", "rename"}:
                current_name = item.get("current_name", item["name"])
                results.append(
                    self.client.update_label(full_name, current_name, payload)
                )
        return results

    def delete(
        self,
        full_name: str,
        label_name: str,
        confirmation: LabelDeleteConfirmation,
    ) -> dict:
        valid = (
            confirmation.acknowledged_impact
            and confirmation.confirm_delete
            and confirmation.repository_full_name == full_name
        )
        if not valid:
            raise IssueDoctorError(
                "LABEL_DELETE_CONFIRMATION_FAILED",
                "删除 Label 需要勾选风险确认、输入完整仓库名并再次确认",
            )
        repository = self.client.get_repository(full_name)
        if repository.get("full_name") != full_name:
            raise IssueDoctorError("GITHUB_WRITE_CONFLICT", "仓库状态校验失败", status_code=409)
        affected = self.client.label_issue_count(full_name, label_name)
        self.client.delete_label(full_name, label_name)
        return {"label": label_name, "affected_issue_count": affected, "deleted": True}
