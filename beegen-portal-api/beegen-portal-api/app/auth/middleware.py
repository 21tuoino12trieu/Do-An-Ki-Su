from typing import Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.keycloak import KeycloakService


security = HTTPBearer(scheme_name="Authorization", auto_error=False)

def validate_allowed_client(claims: Dict) -> None:
    token_client_ids = {
        value
        for value in (claims.get("client_id"), claims.get("azp"))
        if isinstance(value, str) and value
    }
    if claims.get("client_id") != "ai_center":
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to access this data",
        )


async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    try:
        keycloak_service = KeycloakService(credentials.credentials)
        claims = keycloak_service.verify_token()
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}")
    validate_allowed_client(claims)
    return claims
