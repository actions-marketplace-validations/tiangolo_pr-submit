import logging
from functools import lru_cache

import jwt

from pr_submit.config import Settings
from pr_submit.models import OIDCClaims

GITHUB_ACTIONS_ISSUER = "https://token.actions.githubusercontent.com"
GITHUB_ACTIONS_JWKS_URL = f"{GITHUB_ACTIONS_ISSUER}/.well-known/jwks"

logger = logging.getLogger(__name__)


class InvalidIdentityError(ValueError):
    pass


@lru_cache
def get_jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(GITHUB_ACTIONS_JWKS_URL)


def verify_oidc_token(
    token: str,
    settings: Settings,
    jwks_client: jwt.PyJWKClient,
) -> OIDCClaims:
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=GITHUB_ACTIONS_ISSUER,
            leeway=30,
        )
        return OIDCClaims.model_validate(payload)
    except (jwt.PyJWTError, ValueError) as error:
        logger.warning("OIDC identity rejected: error=%s", type(error).__name__)
        raise InvalidIdentityError(
            "The GitHub Actions identity is not allowed"
        ) from error
