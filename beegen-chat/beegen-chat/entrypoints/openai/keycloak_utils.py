# import jwt
import json
import time
import requests
from jose import jwk, jwt
from keycloak import KeycloakOpenID

from beegenerate.configs import KeycloakConfig
from beegenerate.loggings import LOGGER


authen_config = KeycloakConfig.default()


KEYCLOAK_BASE_URL = authen_config.keycloak_base
REALM_NAME = authen_config.realm_name
CLIENT_ID = authen_config.client_id
CLIENT_SECRET_KEY = authen_config.client_secret_key

public_key = None
count = 1
while count <= 10:
    time.sleep(1)
    try:
        jwks_url = '{}realms/{}/protocol/openid-connect/certs'.format(KEYCLOAK_BASE_URL, REALM_NAME)
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
                LOGGER.info(f"Get public key of Keycloak successfully",
                            extra={"clientMessageId": "keycloak-public-key", "status_code": 100})
                # Log the public key value
                LOGGER.info(f"Public Key: {public_key.to_pem().decode('utf-8')}")
                break
    except Exception as e:
        LOGGER.error(e, extra={"clientMessageId": "keycloak-public-key", "status_code": 500})

    count += 1
    if count == 11:
        LOGGER.error("Can not get public key of Keycloak",
                     extra={"clientMessageId": "keycloak-public-key", "status_code": 500})
        break


class KeycloakMiddleware:
    
    def __init__(self, token):
        self.keycloak_openid = KeycloakOpenID(
            server_url=KEYCLOAK_BASE_URL,
            client_id=CLIENT_ID,
            realm_name=REALM_NAME,
            client_secret_key=CLIENT_SECRET_KEY
        )
        self.token = token

    def verify_token(self):
        if not public_key:
            LOGGER.info("public key is Null", extra={"clientMessageId": "keycloak-public-error", "status_code": 500})
            error = json.dumps(jwks)
            raise Exception("Public key is Null. " + error)
        try:
            decoded_token = jwt.decode(self.token, public_key, algorithms=['RS256'])
            return decoded_token
        except Exception as e:
            raise e
