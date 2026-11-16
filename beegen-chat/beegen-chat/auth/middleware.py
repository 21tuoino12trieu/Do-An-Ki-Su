"""
Authentication middleware for FastAPI.
"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from beegenerate.configs import LogConfig
from beegenerate.loggings import LOGGER

from .keycloak import KeycloakMiddleware


# Security scheme for Bearer authentication
security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Dependency for verifying authentication tokens.
    
    Args:
        credentials: HTTP Authorization credentials containing the Bearer token
        
    Returns:
        dict: The decoded token if valid
        
    Raises:
        HTTPException: If token verification fails
    """
    try:
        keycloak_middleware = KeycloakMiddleware(credentials.credentials)
        decoded_token = keycloak_middleware.verify_token()
        return decoded_token
    except Exception as e:
        LOGGER.error(f"Token verification failed: {str(e)}")
        raise HTTPException(
            status_code=401, 
            detail=f"Authentication failed: {str(e)}"
        )