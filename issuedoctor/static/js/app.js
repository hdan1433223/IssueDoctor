(() => {
  const repositoryInput = document.getElementById("repository-url");
  if (!repositoryInput) return;

  document.querySelectorAll("[data-repository]").forEach((button) => {
    button.addEventListener("click", () => {
      repositoryInput.value = button.dataset.repository;
      repositoryInput.focus();
    });
  });
})();
