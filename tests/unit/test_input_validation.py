import pytest

from issuedoctor.errors import IssueDoctorError
from issuedoctor.security.input_validation import parse_github_repository_url


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://github.com/openai/openai-python", "openai/openai-python"),
        ("https://github.com/pallets/flask.git", "pallets/flask"),
        ("psf/requests", "psf/requests"),
        ("pallets/flask.git", "pallets/flask"),
    ],
)
def test_parse_supported_github_urls(value, expected):
    assert parse_github_repository_url(value).full_name == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://github.com/owner/repo",
        "https://gitlab.com/owner/repo",
        "https://github.example.com/owner/repo",
        "https://github.com/owner/repo/issues",
        "https://github.com/owner/../repo",
        "https://github.com/owner/repo?token=secret",
        "https://user:pass@github.com/owner/repo",
        "owner/repo/issues",
        "github.com/owner/repo",
    ],
)
def test_reject_unsupported_or_dangerous_repository_urls(value):
    with pytest.raises(IssueDoctorError, match="仓库|GitHub"):
        parse_github_repository_url(value)
