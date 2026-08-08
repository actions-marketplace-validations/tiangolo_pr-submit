import base64
import json
import logging
from collections.abc import Callable

import httpx
import pytest

from pr_submit.config import Settings
from pr_submit.github import GitHubAPIError, WorkflowNotAllowedError, create_token
from pr_submit.models import OIDCClaims


def github_transport(
    claims: OIDCClaims,
    update: Callable[[httpx.Request, dict[str, object]], None] | None = None,
) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        data: dict[str, object]
        if path.endswith("/installation"):
            data = {"id": 987}
        elif path.endswith("/access_tokens"):
            assert json.loads(request.content) == {
                "repository_ids": [claims.repository_id],
                "permissions": {
                    "contents": "write",
                    "issues": "write",
                    "pull_requests": "write",
                },
            }
            data = {
                "token": "ghs_secret",
                "expires_at": "2026-08-06T15:00:00Z",
                "permissions": {
                    "contents": "write",
                    "issues": "write",
                    "metadata": "read",
                    "pull_requests": "write",
                },
                "repository_selection": "selected",
                "repositories": [{"id": claims.repository_id}],
            }
        elif path == "/repos/fastapi/fastapi":
            data = {"default_branch": "master"}
        elif path.endswith("/.github/pr-submit.yml"):
            content = b"workflows:\n  - .github/workflows/prepare-release.yml\n"
            data = {
                "type": "file",
                "sha": "config-sha",
                "encoding": "base64",
                "content": base64.b64encode(content).decode(),
            }
        elif path.endswith("/permission"):
            data = {"permission": "write", "user": {"id": claims.actor_id}}
        elif path.endswith("/.github/workflows/prepare-release.yml"):
            data = {
                "type": "file",
                "sha": "workflow-blob-sha",
                "encoding": "base64",
                "content": "",
            }
        else:
            raise AssertionError(path)
        if update is not None:
            update(request, data)
        return httpx.Response(200, json=data, request=request)

    return httpx.MockTransport(handle)


def test_create_token(
    settings: Settings, claims: OIDCClaims, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    with httpx.Client(
        base_url="https://api.github.test",
        transport=github_transport(claims),
    ) as client:
        response = create_token(claims, settings, client)
    assert response.token == "ghs_secret"
    assert response.repository == claims.repository
    assert response.permissions == {
        "contents": "write",
        "issues": "write",
        "metadata": "read",
        "pull_requests": "write",
    }
    assert "Installation token issued" in caplog.text
    assert claims.repository in caplog.text
    assert claims.workflow_path in caplog.text
    assert "ghs_secret" not in caplog.text


def test_allows_schedule_without_actor_lookup(
    settings: Settings, claims: OIDCClaims
) -> None:
    scheduled_claims = claims.model_copy(update={"event_name": "schedule"})

    def update(request: httpx.Request, data: dict[str, object]) -> None:
        assert not request.url.path.endswith("/permission")

    with httpx.Client(
        base_url="https://api.github.test",
        transport=github_transport(scheduled_claims, update),
    ) as client:
        create_token(scheduled_claims, settings, client)


@pytest.mark.parametrize(
    ("match_path", "field", "value", "reason"),
    [
        ("/permission", "user", {"id": 1}, "actor ID does not match"),
        ("/permission", "permission", "read", "actor does not have write permission"),
    ],
)
def test_rejects_unauthorized_actor(
    settings: Settings,
    claims: OIDCClaims,
    match_path: str,
    field: str,
    value: object,
    reason: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def update(request: httpx.Request, data: dict[str, object]) -> None:
        if match_path in request.url.path:
            data[field] = value

    with (
        httpx.Client(
            base_url="https://api.github.test",
            transport=github_transport(claims, update),
        ) as client,
        pytest.raises(WorkflowNotAllowedError),
    ):
        create_token(claims, settings, client)
    assert reason in caplog.text
    assert claims.repository in caplog.text
    assert "ghs_secret" not in caplog.text


def test_rejects_non_default_branch(settings: Settings, claims: OIDCClaims) -> None:
    branch_claims = claims.model_copy(update={"ref": "refs/heads/other"})
    with (
        httpx.Client(
            base_url="https://api.github.test",
            transport=github_transport(branch_claims),
        ) as client,
        pytest.raises(WorkflowNotAllowedError),
    ):
        create_token(branch_claims, settings, client)


def test_rejects_changed_workflow(settings: Settings, claims: OIDCClaims) -> None:
    calls = 0

    def update(request: httpx.Request, data: dict[str, object]) -> None:
        nonlocal calls
        if request.url.path.endswith("prepare-release.yml"):
            calls += 1
            if calls == 2:
                data["sha"] = "changed"

    with (
        httpx.Client(
            base_url="https://api.github.test",
            transport=github_transport(claims, update),
        ) as client,
        pytest.raises(WorkflowNotAllowedError),
    ):
        create_token(claims, settings, client)


def test_hides_github_http_error(settings: Settings, claims: OIDCClaims) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    with (
        httpx.Client(
            base_url="https://api.github.test",
            transport=httpx.MockTransport(handle),
        ) as client,
        pytest.raises(GitHubAPIError, match="GitHub rejected"),
    ):
        create_token(claims, settings, client)


def test_rejects_unexpected_token_scope(settings: Settings, claims: OIDCClaims) -> None:
    def update(request: httpx.Request, data: dict[str, object]) -> None:
        if request.url.path.endswith("access_tokens"):
            data["repository_selection"] = "all"

    with (
        httpx.Client(
            base_url="https://api.github.test",
            transport=github_transport(claims, update),
        ) as client,
        pytest.raises(GitHubAPIError),
    ):
        create_token(claims, settings, client)


@pytest.mark.parametrize(
    "match_path",
    [
        "/installation",
        "/access_tokens",
        "/repos/fastapi/fastapi",
        "/.github/pr-submit.yml",
    ],
)
def test_rejects_invalid_github_responses(
    settings: Settings, claims: OIDCClaims, match_path: str
) -> None:
    def update(request: httpx.Request, data: dict[str, object]) -> None:
        if request.url.path.endswith(match_path):
            data.clear()

    with (
        httpx.Client(
            base_url="https://api.github.test",
            transport=github_transport(claims, update),
        ) as client,
        pytest.raises((GitHubAPIError, WorkflowNotAllowedError)),
    ):
        create_token(claims, settings, client)


def test_rejects_workflow_missing_from_config(
    settings: Settings, claims: OIDCClaims
) -> None:
    def update(request: httpx.Request, data: dict[str, object]) -> None:
        if request.url.path.endswith("pr-submit.yml"):
            content = b"workflows:\n  - .github/workflows/other.yml\n"
            data["content"] = base64.b64encode(content).decode()

    with (
        httpx.Client(
            base_url="https://api.github.test",
            transport=github_transport(claims, update),
        ) as client,
        pytest.raises(WorkflowNotAllowedError),
    ):
        create_token(claims, settings, client)


def test_rejects_invalid_config(settings: Settings, claims: OIDCClaims) -> None:
    def update(request: httpx.Request, data: dict[str, object]) -> None:
        if request.url.path.endswith("pr-submit.yml"):
            data["content"] = base64.b64encode(b"unexpected: true\n").decode()

    with (
        httpx.Client(
            base_url="https://api.github.test",
            transport=github_transport(claims, update),
        ) as client,
        pytest.raises(WorkflowNotAllowedError),
    ):
        create_token(claims, settings, client)
