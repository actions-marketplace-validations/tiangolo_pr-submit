from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)

from pr_submit.config import Settings
from pr_submit.models import OIDCClaims


@pytest.fixture(scope="session")
def private_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()


@pytest.fixture(scope="session")
def public_key(private_key: str) -> str:
    key = load_pem_private_key(private_key.encode(), password=None)
    return (
        key.public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )


@pytest.fixture
def settings(private_key: str) -> Settings:
    return Settings(
        github_client_id="Iv1.client",
        github_app_private_key=private_key,
        oidc_audience="https://pr-submit.example.com",
    )


@pytest.fixture
def claims() -> OIDCClaims:
    now = int(datetime.now(UTC).timestamp())
    return OIDCClaims(
        repository="fastapi/fastapi",
        repository_id=75369425,
        actor="tiangolo",
        actor_id=1326112,
        workflow_ref=(
            "fastapi/fastapi/.github/workflows/prepare-release.yml@refs/heads/master"
        ),
        workflow_sha="workflow-sha",
        event_name="workflow_dispatch",
        ref="refs/heads/master",
        exp=now + 300,
        iat=now - 10,
        nbf=now - 10,
    )
