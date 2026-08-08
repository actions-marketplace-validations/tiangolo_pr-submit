from typing import cast

import jwt
import pytest

from pr_submit.config import Settings
from pr_submit.models import OIDCClaims
from pr_submit.security import InvalidIdentityError, verify_oidc_token


class StaticSigningKey:
    def __init__(self, key: str) -> None:
        self.key = key


class StaticJWKClient:
    def __init__(self, public_key: str) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> StaticSigningKey:
        return StaticSigningKey(self.public_key)


def jwks_client(public_key: str) -> jwt.PyJWKClient:
    return cast(jwt.PyJWKClient, StaticJWKClient(public_key))


def encode(claims: OIDCClaims, private_key: str) -> str:
    return jwt.encode(
        {
            **claims.model_dump(),
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "https://pr-submit.example.com",
        },
        private_key,
        algorithm="RS256",
    )


def test_verify_identity(
    settings: Settings,
    claims: OIDCClaims,
    private_key: str,
    public_key: str,
) -> None:
    assert (
        verify_oidc_token(
            encode(claims, private_key), settings, jwks_client(public_key)
        )
        == claims
    )


def test_verify_rejects_token(settings: Settings, public_key: str) -> None:
    with pytest.raises(InvalidIdentityError):
        verify_oidc_token("invalid", settings, jwks_client(public_key))
