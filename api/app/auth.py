"""Authentication and authorization helpers for Centinela."""

import json
from base64 import b64decode


ANALYST_ROLE_NAME = "Analyst"


def principal_roles(x_ms_client_principal: str | None) -> set[str]:
    if not x_ms_client_principal:
        return set()

    try:
        decoded = b64decode(x_ms_client_principal)
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_identity_context") from exc

    role_claim_type = payload.get("role_typ") or "roles"
    roles: set[str] = set()
    for claim in payload.get("claims", []):
        claim_type = claim.get("typ")
        claim_value = claim.get("val")
        if claim_type in {"roles", "role", role_claim_type} and claim_value:
            roles.add(str(claim_value))
    return roles


def require_analyst_access(x_ms_client_principal: str | None) -> None:
    roles = principal_roles(x_ms_client_principal)
    if ANALYST_ROLE_NAME not in roles:
        raise PermissionError("analyst_role_required")