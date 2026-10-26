import os
from collections.abc import MutableMapping
from typing import Protocol

import keyring

SERVICE_NAME = "IssueDoctor"
GITHUB_TOKEN = "github_token"  # nosec B105
LLM_API_KEY = "llm_api_key"
ENVIRONMENT_KEYS = {
    GITHUB_TOKEN: "ISSUEDOCTOR_GITHUB_TOKEN",
    LLM_API_KEY: "ISSUEDOCTOR_LLM_API_KEY",
}


class SecretStore(Protocol):
    persistent: bool

    def get(self, username: str) -> str | None: ...

    def set(self, username: str, value: str) -> None: ...

    def delete(self, username: str) -> None: ...


class KeyringSecretStore:
    persistent = True

    def __init__(self, backend=keyring) -> None:
        self._backend = backend

    def get(self, username: str) -> str | None:
        return self._backend.get_password(SERVICE_NAME, username)

    def set(self, username: str, value: str) -> None:
        self._backend.set_password(SERVICE_NAME, username, value)

    def delete(self, username: str) -> None:
        try:
            self._backend.delete_password(SERVICE_NAME, username)
        except keyring.errors.PasswordDeleteError:
            pass


class EnvironmentSecretStore:
    """Container-safe store: environment has priority, UI values are process-only."""

    persistent = False

    def __init__(
        self,
        environment: MutableMapping[str, str] | None = None,
        volatile: MutableMapping[str, str] | None = None,
    ) -> None:
        self._environment = environment if environment is not None else os.environ
        self._volatile = volatile if volatile is not None else {}

    def get(self, username: str) -> str | None:
        env_name = ENVIRONMENT_KEYS[username]
        return self._environment.get(env_name) or self._volatile.get(username)

    def set(self, username: str, value: str) -> None:
        self._volatile[username] = value

    def delete(self, username: str) -> None:
        self._volatile.pop(username, None)


class MemorySecretStore:
    persistent = False

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, username: str) -> str | None:
        return self.values.get(username)

    def set(self, username: str, value: str) -> None:
        self.values[username] = value

    def delete(self, username: str) -> None:
        self.values.pop(username, None)


def build_secret_store(config: dict) -> SecretStore:
    if config.get("TESTING"):
        return MemorySecretStore()
    if config.get("DOCKER_MODE"):
        return EnvironmentSecretStore()
    return KeyringSecretStore()
