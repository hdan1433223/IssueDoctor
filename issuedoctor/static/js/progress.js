(() => {
  const root = document.querySelector("[data-progress-root]");
  if (!root) return;
  const terminal = new Set(["SUCCEEDED", "PARTIAL", "FAILED", "INTERRUPTED"]);

  async function update() {
    const response = await fetch(`/api/analyses/${root.dataset.runId}/status`);
    const data = await response.json();
    root.querySelector("[data-progress-bar]").style.width = `${data.progress_percent}%`;
    root.querySelector("[role=progressbar]").setAttribute("aria-valuenow", data.progress_percent);
    root.querySelector("[data-current-stage]").textContent = data.current_stage;
    root.querySelector("[data-percent]").textContent = `${data.progress_percent}%`;
    root.querySelector("[data-issue-count]").textContent = data.issue_count;
    root.querySelector("[data-pr-count]").textContent = data.pr_count;
    root.querySelector("[data-comment-count]").textContent = data.comment_count;
    root.querySelector("[data-events]").innerHTML = data.events.map((event) =>
      `<li class="border-l-2 border-line pl-4"><span class="text-slate-500">${event.percent}%</span> ${escapeHtml(event.message)}</li>`
    ).join("");
    if (data.error) {
      const warning = root.querySelector("[data-warning]");
      warning.textContent = `${data.error.code}: ${data.error.message}`;
      warning.classList.remove("hidden");
    }
    if (!terminal.has(data.status)) {
      window.setTimeout(update, 1000);
    } else if (data.status === "SUCCEEDED" || data.status === "PARTIAL") {
      window.setTimeout(() => window.location.assign(`/analysis/${root.dataset.runId}`), 800);
    }
  }

  function escapeHtml(value) {
    const node = document.createElement("span");
    node.textContent = value;
    return node.innerHTML;
  }

  update().catch(() => {
    const warning = root.querySelector("[data-warning]");
    warning.textContent = "进度连接暂时中断，请刷新页面重试。";
    warning.classList.remove("hidden");
  });
})();
