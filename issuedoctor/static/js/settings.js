(() => {
  const form = document.getElementById("settings-form");
  if (!form) return;
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const saveStatus = document.getElementById("settings-status");
  const githubStatus = document.getElementById("github-status");
  const llmStatus = document.getElementById("llm-status");
  const githubInput = document.getElementById("github-token");
  const llmInput = document.getElementById("llm-api-key");
  const githubSavedState = document.getElementById("github-saved-state");
  const llmSavedState = document.getElementById("llm-saved-state");

  const values = () => ({
    github_token: document.getElementById("github-token").value,
    llm_base_url: document.getElementById("llm-base-url").value,
    llm_model: document.getElementById("llm-model").value,
    llm_api_key: document.getElementById("llm-api-key").value
  });

  function showStatus(element, message, tone = "neutral") {
    element.textContent = message;
    element.className = `mt-3 text-sm ${
      tone === "success" ? "text-success" : tone === "error" ? "text-red-700" : "text-slate-600"
    }`;
  }

  function setSavedState(element, saved, savedLabel, emptyLabel) {
    element.textContent = saved ? savedLabel : emptyLabel;
    element.className = `text-xs ${saved ? "text-success" : "text-slate-500"}`;
  }

  async function request(path, body, statusElement, button, pendingText) {
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = pendingText;
    showStatus(statusElement, pendingText);
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify(body)
      });
      const contentType = response.headers.get("content-type") || "";
      const result = contentType.includes("application/json")
        ? await response.json()
        : { ok: false, message: `服务器返回异常（HTTP ${response.status}）` };
      const succeeded = response.ok && result.ok && result.model_available !== false;
      const message = result.message || (succeeded ? "操作成功" : "操作失败");
      showStatus(statusElement, message, succeeded ? "success" : "error");
      return { ...result, ok: succeeded };
    } catch (error) {
      showStatus(statusElement, `请求失败：${error.message || "请检查网络并重试"}`, "error");
      return { ok: false };
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    const result = await request(
      "/api/settings",
      values(),
      saveStatus,
      button,
      "正在保存…"
    );
    if (result.ok) {
      githubInput.value = "";
      llmInput.value = "";
      githubInput.placeholder = result.settings.github_token_saved
        ? "已安全保存；留空将保留当前 Token"
        : "尚未保存 Token";
      llmInput.placeholder = result.settings.llm_api_key_saved
        ? "已安全保存；留空将保留当前 API Key"
        : "尚未保存 API Key";
      setSavedState(
        githubSavedState,
        result.settings.github_token_saved,
        "已配置 Token",
        "未配置 Token（公开仓库仍可只读分析）"
      );
      setSavedState(
        llmSavedState,
        result.settings.llm_api_key_saved,
        "已配置 API Key",
        "未配置，运行基础诊断模式"
      );
      showStatus(
        saveStatus,
        "设置已保存。密钥输入框已按安全规则清空，但已保存的密钥仍然有效。",
        "success"
      );
    }
  });

  form.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    if (!action) return;
    const actions = {
      "test-github": ["/api/settings/test-github", values(), githubStatus, "正在测试…"],
      "test-llm": ["/api/settings/test-llm", values(), llmStatus, "正在测试…"],
      "delete-github": ["/api/settings/delete-github-token", {}, githubStatus, "正在删除…"],
      "delete-llm": ["/api/settings/delete-llm-key", {}, llmStatus, "正在删除…"]
    };
    if (!actions[action]) return;
    const [path, body, statusElement, pendingText] = actions[action];
    const result = await request(path, body, statusElement, button, pendingText);
    if (!result.ok) return;
    if (action === "delete-github") {
      githubInput.value = "";
      githubInput.placeholder = "尚未保存 Token";
      setSavedState(
        githubSavedState,
        false,
        "已配置 Token",
        "未配置 Token（公开仓库仍可只读分析）"
      );
    } else if (action === "delete-llm") {
      llmInput.value = "";
      llmInput.placeholder = "尚未保存 API Key";
      setSavedState(llmSavedState, false, "已配置 API Key", "未配置，运行基础诊断模式");
    }
  });
})();
