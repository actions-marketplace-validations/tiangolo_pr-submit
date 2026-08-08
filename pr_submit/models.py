import base64
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONFIG_PATH = ".github/pr-submit.yml"


class OIDCClaims(BaseModel):
    repository: str
    repository_id: int
    actor: str
    actor_id: int
    workflow_ref: str
    workflow_sha: str
    event_name: Literal["schedule", "workflow_dispatch"]
    ref: str = Field(pattern=r"^refs/heads/.+$")
    exp: int
    iat: int
    nbf: int

    @property
    def workflow_path(self) -> str:
        prefix = f"{self.repository}/"
        if not self.workflow_ref.startswith(prefix):
            raise ValueError("Unexpected workflow repository")
        path_and_ref = self.workflow_ref.removeprefix(prefix)
        path, separator, _ = path_and_ref.rpartition("@")
        if not separator or not path.startswith(".github/workflows/"):
            raise ValueError("Unexpected workflow path")
        return path


class Repository(BaseModel):
    default_branch: str


class Installation(BaseModel):
    id: int


class TokenRepository(BaseModel):
    id: int


class InstallationToken(BaseModel):
    token: str
    expires_at: datetime
    permissions: dict[str, str]
    repository_selection: str
    repositories: list[TokenRepository]


class RepositoryFile(BaseModel):
    type: Literal["file"]
    sha: str
    encoding: Literal["base64"]
    content: str

    def decoded_content(self) -> bytes:
        return base64.b64decode(self.content)


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflows: list[str] = Field(min_length=1)


class GitHubUser(BaseModel):
    id: int


class CollaboratorPermission(BaseModel):
    permission: Literal["admin", "write", "read", "none"]
    user: GitHubUser


class OIDCTokenResponse(BaseModel):
    value: str


class TokenResponse(BaseModel):
    token: str
    expires_at: datetime
    repository: str
    permissions: dict[str, str]
