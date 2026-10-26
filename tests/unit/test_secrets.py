import keyring

from issuedoctor.security.redaction import REDACTED, redact_secret
from issuedoctor.security.secrets import (
    GITHUB_TOKEN,
    LLM_API_KEY,
    EnvironmentSecretStore,
    KeyringSecretStore,
    MemorySecretStore,
    build_secret_store,
)


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, value):
        self.values[(service, username)] = value

    def delete_password(self, service, username):
        self.values.pop((service, username), None)


def test_keyring_store_round_trip_and_delete():
    backend = FakeKeyring()
    store = KeyringSecretStore(backend)

    store.set(GITHUB_TOKEN, "github-secret")
    assert store.get(GITHUB_TOKEN) == "github-secret"
    store.delete(GITHUB_TOKEN)
    assert store.get(GITHUB_TOKEN) is None


def test_environment_has_priority_and_ui_value_is_volatile():
    environment = {"ISSUEDOCTOR_LLM_API_KEY": "environment-secret"}
    volatile = {}
    store = EnvironmentSecretStore(environment, volatile)

    store.set(LLM_API_KEY, "ui-secret")

    assert store.get(LLM_API_KEY) == "environment-secret"
    assert volatile[LLM_API_KEY] == "ui-secret"

    environment.clear()
    assert store.get(LLM_API_KEY) == "ui-secret"
    store.delete(LLM_API_KEY)
    assert store.get(LLM_API_KEY) is None


def test_keyring_delete_ignores_missing_password():
    class MissingKeyring(FakeKeyring):
        def delete_password(self, service, username):
            raise keyring.errors.PasswordDeleteError("missing")

    KeyringSecretStore(MissingKeyring()).delete(GITHUB_TOKEN)


def test_memory_store_and_store_factory():
    store = MemorySecretStore()
    store.set(GITHUB_TOKEN, "value")
    assert store.get(GITHUB_TOKEN) == "value"
    store.delete(GITHUB_TOKEN)
    assert store.get(GITHUB_TOKEN) is None

    assert isinstance(build_secret_store({"TESTING": True}), MemorySecretStore)
    assert isinstance(build_secret_store({"DOCKER_MODE": True}), EnvironmentSecretStore)
    assert isinstance(build_secret_store({}), KeyringSecretStore)


def test_redaction_covers_headers_nested_values_and_query_parameters():
    value = {
        "Authorization": "Bearer abc.def-123",
        "nested": ["https://example.test?a=1&api_key=secret", "Token xyz"],
    }

    result = redact_secret(value)

    assert result["Authorization"] == REDACTED
    assert "secret" not in result["nested"][0]
    assert result["nested"][1] == f"Token {REDACTED}"
    assert redact_secret(("plain", 3)) == ("plain", 3)
