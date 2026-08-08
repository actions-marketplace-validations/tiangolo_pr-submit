import sys
from pathlib import Path

import httpx
from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from pr_submit.models import OIDCTokenResponse, TokenResponse

DEFAULT_SERVICE_URL = "https://pr-submit.fastapicloud.dev"


class ActionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_ignore_empty=True)

    input_url: str = DEFAULT_SERVICE_URL
    actions_id_token_request_url: str
    actions_id_token_request_token: SecretStr
    github_output: Path


class ActionError(RuntimeError):
    pass


def get_oidc_token(settings: ActionSettings, client: httpx.Client) -> str:
    try:
        response = client.get(
            settings.actions_id_token_request_url,
            headers={
                "Authorization": (
                    "Bearer "
                    f"{settings.actions_id_token_request_token.get_secret_value()}"
                )
            },
            params={"audience": settings.input_url},
        )
        response.raise_for_status()
        return OIDCTokenResponse.model_validate_json(response.content).value
    except (httpx.HTTPError, ValidationError) as error:
        raise ActionError("GitHub did not issue an OIDC token") from error


def get_installation_token(
    settings: ActionSettings,
    oidc_token: str,
    client: httpx.Client,
) -> str:
    try:
        response = client.post(
            f"{settings.input_url.rstrip('/')}/token",
            headers={"Authorization": f"Bearer {oidc_token}"},
        )
        response.raise_for_status()
        return TokenResponse.model_validate_json(response.content).token
    except (httpx.HTTPError, ValidationError) as error:
        raise ActionError("PR Submit did not issue an installation token") from error


def run(settings: ActionSettings, client: httpx.Client) -> None:
    oidc_token = get_oidc_token(settings, client)
    token = get_installation_token(settings, oidc_token, client)
    print(f"::add-mask::{token}")
    with settings.github_output.open("a", encoding="utf-8") as output_file:
        output_file.write(f"token={token}\n")


def main() -> None:
    try:
        settings = ActionSettings()
        with httpx.Client(timeout=10) as client:
            run(settings, client)
    except (ValidationError, ActionError) as error:
        print(f"::error::{error}")
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
