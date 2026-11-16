import os
import time

import requests
from jose import jwk, jwt
from keycloak import KeycloakOpenID


class KeycloakConfig:
    def __init__(self):
        self.keycloak_base_url = os.getenv("KEYCLOAK_BASE_URL", "")
        self.realm_name = os.getenv("KEYCLOAK_REALM", "")
        self.client_id = os.getenv("KEYCLOAK_CLIENT_ID", "")
        self.client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET", "")


def _normalize_base_url(base_url: str) -> str:
    if not base_url:
        return base_url
    return base_url if base_url.endswith("/") else f"{base_url}/"


def _initialize_public_key(base_url: str, realm_name: str):
    public_key = None
    max_retries = 10
    retry_count = 1

    while retry_count <= max_retries:
        time.sleep(1)
        try:
            jwks_url = f"{base_url}realms/{realm_name}/protocol/openid-connect/certs"
            jwks = requests.get(jwks_url).json()

            if "error" in jwks:
                public_key = None
            else:
                jwk_dict = jwks.get("keys", [])
                key = None
                for jwk_ in jwk_dict:
                    if jwk_.get("use") == "sig":
                        key = jwk_
                if key:
                    public_key = jwk.construct(key)
                    return public_key
        except Exception:
            public_key = None

        retry_count += 1

    return None


class KeycloakService:
    def __init__(self, token: str, config: KeycloakConfig | None = None):
        self.config = config or KeycloakConfig()
        self.base_url = _normalize_base_url(self.config.keycloak_base_url)
        self.keycloak_openid = KeycloakOpenID(
            server_url=self.base_url,
            client_id=self.config.client_id,
            realm_name=self.config.realm_name,
            client_secret_key=self.config.client_secret,
        )
        self.token = token
        self.public_key = _initialize_public_key(self.base_url, self.config.realm_name)

    def verify_token(self):
        if not self.public_key:
            raise Exception("Public key is not available")
        return jwt.decode(self.token, self.public_key, algorithms=["RS256"])
