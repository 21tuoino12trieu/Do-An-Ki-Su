from beegenerate.configs.yaml_model import YamlModel
from beegenerate.const import BEEGEN_ROOT


class KeycloakConfig(YamlModel):
    """
    Configuration class for authentication settings.

    This class inherits from YamlModel and defines the structure for
    authentication configuration, particularly for Keycloak integration.

    Attributes:
        keycloak_base (str): The base URL for the Keycloak server.
        realm_name (str): The name of the Keycloak realm to be used.
        client_id (str): The client ID for the application in Keycloak.
        client_secret_key (str): The client secret key for the application in Keycloak.
        jwt_secret_key (str): The secret key used for JWT token signing/verification.

    Example:
        config = AuthenConfig(
            keycloak_base="https://keycloak.example.com",
            realm_name="my-realm",
            client_id="my-client",
            client_secret_key="secret-key",
            jwt_secret_key="jwt-secret"
        )
    """
    keycloak_base: str
    realm_name: str
    client_id: str
    client_secret_key: str
    jwt_secret_key: str
    
    @classmethod
    def default(cls) -> 'KeycloakConfig':
        """Load default config"""
        dict = KeycloakConfig.read_yaml(BEEGEN_ROOT / "config/authen.yaml")
        return KeycloakConfig(**dict)
    
if __name__ == "__main__":
    # log_config.to_yaml_file(Path('log_config.yaml'))
    config = KeycloakConfig.default()
    print(config)