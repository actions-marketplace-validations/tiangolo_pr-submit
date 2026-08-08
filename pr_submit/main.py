import logging
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pr_submit.config import Settings, get_settings
from pr_submit.github import (
    GITHUB_API_URL,
    GitHubAPIError,
    WorkflowNotAllowedError,
    create_token,
)
from pr_submit.models import OIDCClaims, TokenResponse
from pr_submit.security import InvalidIdentityError, get_jwks_client, verify_oidc_token

logger = logging.getLogger(__name__)

SettingsDep = Annotated[Settings, Depends(get_settings)]
JWKSClientDep = Annotated[jwt.PyJWKClient, Depends(get_jwks_client)]
BearerCredentialsDep = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(HTTPBearer(auto_error=False)),
]

with (Path(__file__).parent.parent / "pyproject.toml").open("rb") as pyproject_file:
    app_version = tomllib.load(pyproject_file)["project"]["version"]

app = FastAPI(title="PR Submit", version=app_version)


def get_claims(
    settings: SettingsDep,
    jwks_client: JWKSClientDep,
    credentials: BearerCredentialsDep,
) -> OIDCClaims:
    if credentials is None:
        logger.warning("Token request rejected: OIDC bearer token is missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A GitHub Actions OIDC bearer token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return verify_oidc_token(credentials.credentials, settings, jwks_client)
    except InvalidIdentityError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error


OIDCClaimsDep = Annotated[OIDCClaims, Depends(get_claims)]


def get_github_client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=GITHUB_API_URL, timeout=10) as client:
        yield client


GitHubClientDep = Annotated[
    httpx.Client,
    Depends(get_github_client, scope="function"),
]


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"name": app.title, "version": app.version}


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/token")
def token(
    claims: OIDCClaimsDep,
    settings: SettingsDep,
    github_client: GitHubClientDep,
    response: Response,
) -> TokenResponse:
    try:
        token_response = create_token(claims, settings, github_client)
    except WorkflowNotAllowedError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The GitHub Actions workflow is not allowed",
        ) from error
    except GitHubAPIError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return token_response
