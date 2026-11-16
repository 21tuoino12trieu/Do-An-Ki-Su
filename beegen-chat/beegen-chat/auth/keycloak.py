"""
Keycloak authentication utilities.
"""
import json
import time
import requests
from jose import jwk, jwt
from keycloak import KeycloakOpenID

from beegenerate.configs import KeycloakConfig, LogConfig
from beegenerate.loggings import LOGGER


# Load authentication configuration
authen_config = KeycloakConfig.default()

# Keycloak configuration
KEYCLOAK_BASE_URL = authen_config.keycloak_base
REALM_NAME = authen_config.realm_name
CLIENT_ID = authen_config.client_id
CLIENT_SECRET_KEY = authen_config.client_secret_key


# Initialize public key with retry logic
def initialize_public_key():
    """Initialize the Keycloak public key with retry mechanism."""
    public_key = None
    max_retries = 10
    retry_count = 1
    
    while retry_count <= max_retries:
        time.sleep(1)
        try:
            jwks_url = f'{KEYCLOAK_BASE_URL}realms/{REALM_NAME}/protocol/openid-connect/certs'
            jwks = requests.get(jwks_url).json()
            
            if 'error' in jwks:
                LOGGER.error(jwks, extra={"clientMessageId": "keycloak-public-key", "status_code": 500})
            else:
                jwk_dict = jwks['keys']
                key = None
                for jwk_ in jwk_dict:
                    if jwk_["use"] == "sig":
                        key = jwk_
                if not key:
                    LOGGER.error("Couldn't find the key corresponding to sig",
                                extra={"clientMessageId": "keycloak-public-key", "status_code": 500})
                    public_key = None
                else:
                    public_key = jwk.construct(key)
                    LOGGER.info("Get public key of Keycloak successfully",
                                extra={"clientMessageId": "keycloak-public-key", "status_code": 100})
                    # Log the public key value
                    LOGGER.info("Public Key: %s", public_key.to_pem().decode('utf-8'))
                    return public_key
        except Exception as e:
            LOGGER.error(e, extra={"clientMessageId": "keycloak-public-key", "status_code": 500})

        retry_count += 1
        
    LOGGER.error("Could not get public key of Keycloak after maximum retries",
                extra={"clientMessageId": "keycloak-public-key", "status_code": 500})
    return None


def generate_internal_jwt():
    url = f"{authen_config.keycloak_base}/realms/ms-core/protocol/openid-connect/token"

    payload = f'client_id={authen_config.client_id}&client_secret={authen_config.client_secret_key}&grant_type=client_credentials'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    return response.json().get('access_token', None)


# Initialize public key
public_key = initialize_public_key()


class KeycloakMiddleware:
    """Middleware for Keycloak token verification."""
    
    def __init__(self, token):
        """
        Initialize the Keycloak middleware.
        
        Args:
            token (str): The JWT token to verify
        """
        self.keycloak_openid = KeycloakOpenID(
            server_url=KEYCLOAK_BASE_URL,
            client_id=CLIENT_ID,
            realm_name=REALM_NAME,
            client_secret_key=CLIENT_SECRET_KEY
        )
        self.token = token

    def verify_token(self):
        """
        Verify the token against Keycloak.
        
        Returns:
            dict: The decoded token if valid
            
        Raises:
            Exception: If the token is invalid or verification fails
        """
        if not public_key:
            LOGGER.error("Public key is not available", 
                         extra={"clientMessageId": "keycloak-public-error", "status_code": 500})
            raise Exception("Public key is not available. Keycloak integration failed during initialization.")
            
        try:
            decoded_token = jwt.decode(self.token, public_key, algorithms=['RS256'])
            return decoded_token
        except Exception as e:
            LOGGER.error(f"Token verification failed: {str(e)}", 
                         extra={"clientMessageId": "keycloak-token-error", "status_code": 401})
            raise e
        
        
if __name__ == "__main__":
    keycloak = KeycloakMiddleware(
        token="""REPLACE_WITH_LOCAL_SECRET"""
    )
    
    keycloak.verify_token()