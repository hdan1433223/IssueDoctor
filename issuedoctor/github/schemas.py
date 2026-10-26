from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RepositoryData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    full_name: str
    html_url: str
    description: str | None = None
    default_branch: str
    language: str | None = None
    stargazers_count: int = 0
    forks_count: int = 0
    archived: bool = False
    has_issues: bool = True
    open_issues_count: int = 0


class ActorData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    login: str


class LabelData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    color: str | None = None
    description: str | None = None


class IssueData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: int
    title: str
    body: str | None = None
    state: str
    html_url: str
    user: ActorData
    author_association: str = "NONE"
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    comments: int = 0
    labels: list[LabelData | str] = Field(default_factory=list)


class PullRequestData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: int
    title: str
    body: str | None = None
    state: str
    html_url: str
    user: ActorData
    author_association: str = "NONE"
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    merged_at: datetime | None = None
    labels: list[LabelData | str] = Field(default_factory=list)


class CommentData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    issue_url: str
    html_url: str
    body: str | None = None
    user: ActorData
    author_association: str = "NONE"
    created_at: datetime
    updated_at: datetime

    @property
    def issue_number(self) -> int:
        return int(self.issue_url.rstrip("/").rsplit("/", 1)[-1])

