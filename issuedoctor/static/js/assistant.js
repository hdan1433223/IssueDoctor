(() => {
  const root = document.querySelector("[data-assistant-root]");
  if (!root) return;
  const launcher = root.querySelector("[data-assistant-launcher]");
  const panel = root.querySelector("[data-assistant-panel]") || root.querySelector("#assistant-panel");
  const closeButton = root.querySelector("[data-assistant-close]");
  const clearButton = root.querySelector("[data-assistant-clear]");
  const form = root.querySelector("[data-assistant-form]");
  const input = root.querySelector("[data-assistant-input]");
  const submit = root.querySelector("[data-assistant-submit]");
  const messages = root.querySelector("[data-assistant-messages]");
  const status = root.querySelector("[data-assistant-status]");
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const positionKey = "issuedoctor.assistant.position.v1";
  const runId = root.dataset.runId || "current";
  const transcriptKey = `issuedoctor.assistant.transcript.${runId}.v1`;
  let busy = false;
  let history = [];
  let transcript = [];
  let suppressClickUntil = 0;
  let dragging = false;
  let dragMoved = false;
  let dragStart = null;

  const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), Math.max(minimum, maximum));

  const setLauncherPosition = (left, top) => {
    const size = launcher.offsetWidth || 56;
    const nextLeft = clamp(left, 8, window.innerWidth - size - 8);
    const nextTop = clamp(top, 8, window.innerHeight - size - 8);
    root.style.left = `${nextLeft}px`;
    root.style.top = `${nextTop}px`;
    root.style.right = "auto";
    root.style.bottom = "auto";
  };

  const saveLauncherPosition = () => {
    const rect = launcher.getBoundingClientRect();
    try {
      window.localStorage.setItem(positionKey, JSON.stringify({
        x: rect.left / Math.max(window.innerWidth, 1),
        y: rect.top / Math.max(window.innerHeight, 1)
      }));
    } catch (_error) {
      // Storage can be disabled; dragging still works for the current page.
    }
  };

  const restoreLauncherPosition = () => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(positionKey) || "null");
      if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
        setLauncherPosition(
          saved.x * window.innerWidth,
          saved.y * window.innerHeight
        );
      }
    } catch (_error) {
      // Ignore malformed or unavailable local storage.
    }
  };

  const positionPanel = () => {
    if (panel.hidden || window.matchMedia("(max-width: 760px)").matches) {
      panel.style.removeProperty("left");
      panel.style.removeProperty("top");
      return;
    }
    const launcherRect = launcher.getBoundingClientRect();
    const width = panel.offsetWidth;
    const height = panel.offsetHeight;
    const gap = 10;
    const edge = 16;
    let left = launcherRect.right - width;
    let top = launcherRect.top - height - gap;
    if (top < edge) top = launcherRect.bottom + gap;
    left = clamp(left, edge, window.innerWidth - width - edge);
    top = clamp(top, edge, window.innerHeight - height - edge);
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
  };

  const setOpen = (open) => {
    panel.hidden = !open;
    root.classList.toggle("is-open", open);
    launcher.setAttribute("aria-expanded", String(open));
    if (open) {
      positionPanel();
      window.setTimeout(() => input.focus(), 0);
    }
    else launcher.focus();
  };

  const addText = (parent, tag, text, className = "") => {
    const element = document.createElement(tag);
    element.textContent = text;
    if (className) element.className = className;
    parent.appendChild(element);
    return element;
  };

  const scrollToLatest = () => {
    messages.scrollTop = messages.scrollHeight;
  };

  const saveTranscript = () => {
    transcript = transcript.slice(-20);
    try {
      window.sessionStorage.setItem(transcriptKey, JSON.stringify({ transcript, history }));
    } catch (_error) {
      // Session storage may be disabled; the current page still keeps the conversation.
    }
  };

  const addUserMessage = (text) => {
    const item = document.createElement("div");
    item.className = "assistant-message is-user";
    item.dataset.persistedMessage = "true";
    addText(item, "p", text);
    messages.appendChild(item);
    scrollToLatest();
  };

  const addAssistantMessage = (result) => {
    const item = document.createElement("div");
    item.className = "assistant-message is-assistant";
    item.dataset.persistedMessage = "true";
    if (result.mode === "extractive") {
      addText(item, "span", "引用式回答", "assistant-mode-badge");
    }
    addText(item, "p", result.answer);
    if (result.key_points?.length) {
      const list = document.createElement("ul");
      result.key_points.forEach((point) => addText(list, "li", point));
      item.appendChild(list);
    }
    if (result.limitations) {
      addText(item, "p", result.limitations, "assistant-limitations");
    }
    if (result.sources?.length) {
      const sources = document.createElement("div");
      sources.className = "assistant-sources";
      addText(sources, "p", "来源", "assistant-sources-title");
      result.sources.forEach((source) => {
        const row = document.createElement("div");
        row.className = "assistant-source";
        addText(row, "span", source.label || "", "assistant-source-label");
        const link = document.createElement("a");
        const localUrl = typeof source.page_url === "string" && source.page_url.startsWith("/");
        const githubUrl = typeof source.github_url === "string" && source.github_url.startsWith("https://github.com/");
        link.href = localUrl ? source.page_url : githubUrl ? source.github_url : "#";
        link.textContent = source.title || "查看报告来源";
        if (!localUrl) {
          link.target = "_blank";
          link.rel = "noopener noreferrer";
        }
        if (!localUrl && !githubUrl) {
          link.addEventListener("click", (event) => event.preventDefault());
        }
        row.appendChild(link);
        sources.appendChild(row);
      });
      item.appendChild(sources);
    }
    messages.appendChild(item);
    scrollToLatest();
  };

  const addErrorMessage = (text) => {
    const item = document.createElement("div");
    item.className = "assistant-message is-error";
    item.dataset.persistedMessage = "true";
    addText(item, "p", text);
    messages.appendChild(item);
    scrollToLatest();
  };

  const restoreTranscript = () => {
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(transcriptKey) || "null");
      if (!saved || !Array.isArray(saved.transcript)) return;
      transcript = saved.transcript.slice(-20);
      history = Array.isArray(saved.history) ? saved.history.slice(-6) : [];
      transcript.forEach((entry) => {
        if (entry?.kind === "user") addUserMessage(String(entry.text || ""));
        else if (entry?.kind === "result" && entry.result) addAssistantMessage(entry.result);
        else if (entry?.kind === "error") addErrorMessage(String(entry.text || "请求失败"));
      });
      if (transcript.length) status.textContent = "已恢复本次报告的对话";
    } catch (_error) {
      transcript = [];
      history = [];
    }
  };

  const clearTranscript = () => {
    if (!transcript.length) return;
    transcript = [];
    history = [];
    try {
      window.sessionStorage.removeItem(transcriptKey);
    } catch (_error) {
      // Nothing else to clear when session storage is unavailable.
    }
    messages.querySelectorAll("[data-persisted-message]").forEach((item) => item.remove());
    status.textContent = "对话已清空";
    input.focus();
  };

  const addLoading = () => {
    const item = document.createElement("div");
    item.className = "assistant-message is-assistant assistant-loading";
    addText(item, "span", "");
    addText(item, "span", "");
    addText(item, "span", "");
    addText(item, "p", "正在检索报告并组织答案…");
    messages.appendChild(item);
    scrollToLatest();
    return item;
  };

  const ask = async (question) => {
    const clean = String(question || "").trim();
    if (!clean || busy) return;
    setOpen(true);
    busy = true;
    submit.disabled = true;
    input.disabled = true;
    status.textContent = "正在检索本次报告…";
    addUserMessage(clean);
    transcript.push({ kind: "user", text: clean });
    saveTranscript();
    const loading = addLoading();
    try {
      const response = await fetch(`/api/analyses/${root.dataset.runId}/assistant/query`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken
        },
        body: JSON.stringify({ question: clean, history })
      });
      const result = await response.json();
      loading.remove();
      if (!response.ok) throw new Error(result.message || "报告助手暂时不可用");
      addAssistantMessage(result);
      history = [
        ...history,
        { role: "user", content: clean },
        { role: "assistant", content: result.answer }
      ].slice(-6);
      transcript.push({ kind: "result", result });
      saveTranscript();
      status.textContent = result.mode === "enhanced"
        ? "已根据报告生成"
        : result.llm_error
          ? "LLM 调用失败，已返回规则摘要"
          : "已返回规则摘要";
    } catch (error) {
      loading.remove();
      const message = error.message || "问答请求失败，请稍后重试。";
      addErrorMessage(message);
      transcript.push({ kind: "error", text: message });
      saveTranscript();
      status.textContent = "请求失败";
    } finally {
      busy = false;
      submit.disabled = false;
      input.disabled = false;
      input.focus();
    }
  };

  restoreLauncherPosition();
  restoreTranscript();

  launcher.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || !panel.hidden) return;
    const rect = launcher.getBoundingClientRect();
    dragStart = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      left: rect.left,
      top: rect.top
    };
    dragging = true;
    dragMoved = false;
    launcher.setPointerCapture(event.pointerId);
  });
  launcher.addEventListener("pointermove", (event) => {
    if (!dragging || !dragStart) return;
    const deltaX = event.clientX - dragStart.x;
    const deltaY = event.clientY - dragStart.y;
    if (!dragMoved && Math.hypot(deltaX, deltaY) < 5) return;
    dragMoved = true;
    root.classList.add("is-dragging");
    setLauncherPosition(dragStart.left + deltaX, dragStart.top + deltaY);
  });
  const finishDrag = (event) => {
    if (!dragging) return;
    dragging = false;
    root.classList.remove("is-dragging");
    if (launcher.hasPointerCapture?.(event.pointerId)) {
      launcher.releasePointerCapture(event.pointerId);
    }
    if (dragMoved) {
      suppressClickUntil = Date.now() + 250;
      saveLauncherPosition();
    }
    dragStart = null;
  };
  launcher.addEventListener("pointerup", finishDrag);
  launcher.addEventListener("pointercancel", finishDrag);
  launcher.addEventListener("click", (event) => {
    if (Date.now() < suppressClickUntil) {
      event.preventDefault();
      return;
    }
    setOpen(panel.hidden);
  });
  launcher.addEventListener("keydown", (event) => {
    if (!event.shiftKey || !["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    const rect = launcher.getBoundingClientRect();
    const delta = event.key === "ArrowLeft" ? -20 : event.key === "ArrowRight" ? 20 : 0;
    const vertical = event.key === "ArrowUp" ? -20 : event.key === "ArrowDown" ? 20 : 0;
    setLauncherPosition(rect.left + delta, rect.top + vertical);
    saveLauncherPosition();
  });
  closeButton.addEventListener("click", () => setOpen(false));
  clearButton?.addEventListener("click", () => {
    if (window.confirm("清空本次报告的问答记录？")) clearTranscript();
  });
  root.querySelectorAll("[data-assistant-question]").forEach((button) => {
    button.addEventListener("click", () => ask(button.dataset.assistantQuestion));
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = input.value;
    input.value = "";
    ask(question);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) setOpen(false);
  });
  window.addEventListener("resize", () => {
    const rect = launcher.getBoundingClientRect();
    if (root.style.left) setLauncherPosition(rect.left, rect.top);
    if (!panel.hidden) positionPanel();
  });
})();
