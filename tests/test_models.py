import pytest
from pydantic import ValidationError

from pr_submit.models import OIDCClaims


def test_claim_properties(claims: OIDCClaims) -> None:
    assert claims.workflow_path == ".github/workflows/prepare-release.yml"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_name", "push"),
        ("ref", "refs/tags/0.1.0"),
    ],
)
def test_claims_reject_unexpected_event_or_ref(
    claims: OIDCClaims, field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        OIDCClaims.model_validate({**claims.model_dump(), field: value})


def test_claims_reject_workflow_repository(claims: OIDCClaims) -> None:
    invalid = claims.model_copy(update={"workflow_ref": "other/repo/x.yml@main"})
    with pytest.raises(ValueError):
        _ = invalid.workflow_path


def test_claims_reject_workflow_path(claims: OIDCClaims) -> None:
    invalid = claims.model_copy(
        update={"workflow_ref": "fastapi/fastapi/not-a-workflow@main"}
    )
    with pytest.raises(ValueError):
        _ = invalid.workflow_path
