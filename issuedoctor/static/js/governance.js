(() => {
  const button = document.querySelector("[data-generate-governance]");
  if (!button) return;
  button.addEventListener("click", async () => {
    const status = document.querySelector("[data-governance-status]");
    button.disabled = true;
    status.textContent = "正在生成并校验治理包…";
    const response = await fetch(`/api/analyses/${button.dataset.runId}/governance/generate`, {
      method: "POST",
      headers: { "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content }
    });
    const result = await response.json();
    if (response.ok) window.location.reload();
    else {
      status.textContent = result.message || "治理包生成失败";
      button.disabled = false;
    }
  });

  const actions = document.querySelector("[data-write-actions]");
  if (!actions) return;
  const token = document.querySelector('meta[name="csrf-token"]').content;
  const packageId = actions.dataset.packageId;
  const repository = actions.dataset.repository;
  const send = async (path, payload) => {
    const response = await fetch(`/api/governance/${packageId}/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    document.querySelector("[data-governance-status]").textContent = result.ok
      ? "操作成功" : (result.message || "操作失败");
    return result;
  };
  const preview = actions.querySelector("[data-confirm-preview]");
  preview.addEventListener("change", () => {
    actions.querySelector("[data-create-pr]").disabled = !preview.checked;
    actions.querySelector("[data-apply-labels]").disabled = !preview.checked;
  });
  actions.querySelector("[data-create-pr]").addEventListener("click", async () => {
    if (window.confirm("确认基于当前 Diff 创建新分支和 Pull Request？")) {
      const result = await send("create-pr", { confirmed: true });
      if (result.pull_request_url) window.open(result.pull_request_url, "_blank", "noopener");
    }
  });
  actions.querySelector("[data-apply-labels]").addEventListener("click", async () => {
    if (window.confirm("确认应用预览中的 Label 新增或更新？")) {
      await send("labels/apply", { confirmed: true });
    }
  });
  actions.querySelector("[data-check-impact]").addEventListener("click", async () => {
    const labelName = actions.querySelector("[data-delete-label-name]").value;
    const result = await send("labels/delete-impact", { label_name: labelName });
    if (result.ok) actions.querySelector("[data-impact-result]").textContent = `当前关联 ${result.affected_issue_count} 个 Issues/PRs。`;
  });
  actions.querySelector("[data-delete-label]").addEventListener("click", async () => {
    const payload = {
      label_name: actions.querySelector("[data-delete-label-name]").value,
      acknowledged_impact: actions.querySelector("[data-ack-impact]").checked,
      repository_full_name: actions.querySelector("[data-repository-confirmation]").value,
      confirm_delete: actions.querySelector("[data-confirm-delete]").checked
    };
    if (payload.repository_full_name !== repository) {
      document.querySelector("[data-governance-status]").textContent = "完整仓库名不匹配";
      return;
    }
    if (window.confirm("最后确认：永久删除该 Label？")) await send("labels/delete", payload);
  });
})();
