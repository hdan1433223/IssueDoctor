(() => {
  const form = document.getElementById("analysis-form");
  if (!form) return;
  const aiCount = document.getElementById("ai-issue-count");
  const updateAIEstimate = () => {
    if (!aiCount) return;
    const requested = Math.max(1, Number(aiCount.value) || 1);
    const estimatedIssues = Math.max(1, Number(aiCount.dataset.estimatedIssues) || requested);
    const selected = Math.min(requested, estimatedIssues);
    const batchSize = Math.max(1, Number(aiCount.dataset.batchSize) || 1);
    const maximumBatches = Math.max(1, Number(aiCount.dataset.maxBatches) || 1);
    form.querySelector("[data-ai-estimated-items]").textContent = selected;
    form.querySelector("[data-ai-estimated-batches]").textContent = Math.min(
      Math.ceil(selected / batchSize),
      maximumBatches
    );
  };
  aiCount?.addEventListener("input", updateAIEstimate);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    const error = form.querySelector("[data-analysis-error]");
    button.disabled = true;
    button.textContent = "正在创建任务…";
    error.textContent = "";
    try {
      const response = await fetch("/api/analyses", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": form.querySelector('[name="csrf_token"]').value
        },
        body: JSON.stringify({
          repository_url: form.dataset.repositoryUrl,
          issue_limit: Number(document.getElementById("issue-limit").value),
          pr_limit: Number(document.getElementById("pr-limit").value),
          ai_issue_count: Number(aiCount.value)
        })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || "无法创建分析任务");
      window.location.assign(`/analysis/${result.id}/progress`);
    } catch (requestError) {
      error.textContent = requestError.message;
      button.disabled = false;
      button.textContent = "开始审计";
    }
  });
})();
