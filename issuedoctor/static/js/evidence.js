(() => {
  const drawer = document.querySelector("[data-evidence-drawer]");
  if (!drawer) return;
  const close = () => drawer.classList.add("hidden");
  document.querySelectorAll("[data-close-drawer]").forEach((button) =>
    button.addEventListener("click", close)
  );
  document.querySelectorAll("[data-evidence]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = JSON.parse(button.dataset.evidence);
      drawer.querySelector("[data-drawer-object]").textContent = item.issue_number
        ? `Issue #${item.issue_number}` : `PR #${item.pr_number}`;
      drawer.querySelector("[data-drawer-type]").textContent = item.type || "";
      drawer.querySelector("[data-drawer-actor]").textContent = [item.actor_login, item.actor_association].filter(Boolean).join(" · ");
      drawer.querySelector("[data-drawer-time]").textContent = item.happened_at || "";
      drawer.querySelector("[data-drawer-excerpt]").textContent = item.excerpt || "";
      drawer.querySelector("[data-drawer-link]").href = item.github_url;
      drawer.classList.remove("hidden");
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
})();

