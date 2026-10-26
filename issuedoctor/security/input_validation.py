import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from issuedoctor.errors import IssueDoctorError

OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


@dataclass(frozen=True)
class RepositoryRef:
    owner: str
    repo: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def html_url(self) -> str:
        return f"https://github.com/{self.full_name}"


def parse_github_repository_url(value: str) -> RepositoryRef:
    candidate = value.strip()
    if "://" not in candidate:
        segments = candidate.strip("/").split("/")
        if len(segments) != 2 or any(segment in {"", ".", ".."} for segment in segments):
            raise IssueDoctorError(
                "INVALID_REPO_URL",
                "请输入 GitHub 仓库简写 owner/repository 或完整链接",
            )
        owner, repo = segments
        if repo.endswith(".git"):
            repo = repo[:-4]
        if not OWNER_PATTERN.fullmatch(owner) or not REPO_PATTERN.fullmatch(repo):
            raise IssueDoctorError("INVALID_REPO_URL", "仓库 owner 或名称格式无效")
        return RepositoryRef(owner=owner, repo=repo)

    parts = urlsplit(candidate)
    if (
        parts.scheme != "https"
        or parts.hostname != "github.com"
        or parts.port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise IssueDoctorError(
            "INVALID_REPO_URL",
            "请输入 GitHub 仓库简写 owner/repository 或完整链接",
        )

    path = unquote(parts.path).strip("/")
    segments = path.split("/")
    if len(segments) != 2 or any(segment in {"", ".", ".."} for segment in segments):
        raise IssueDoctorError("INVALID_REPO_URL", "仓库地址必须只包含 owner 和 repository")
    owner, repo = segments
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not OWNER_PATTERN.fullmatch(owner) or not REPO_PATTERN.fullmatch(repo):
        raise IssueDoctorError("INVALID_REPO_URL", "仓库 owner 或名称格式无效")
    return RepositoryRef(owner=owner, repo=repo)
