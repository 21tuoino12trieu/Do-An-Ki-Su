from typing import Annotated
from fastapi import HTTPException, status, Depends
from pymongo.collection import Collection
from beegen_v1.configs.mcp.mcp_config import RootMCPConfig
from beemcp.utils import encrypt, decrypt


from beegenerate.loggings import LOGGER


class UserService:
    """
    Service class for user management operations using MongoDB.

    Provides methods to retrieve user information, set encrypted JIRA tokens,
    and retrieve/decrypt tokens for users. Handles error logging and integrates
    with FastAPI exception handling.
    """

    def __init__(self, mongodb):
        """
        Initialize the UserService.

        Args:
            mongodb: The MongoDB client or database instance.
        """
        self.mongodb = mongodb
        self.root_mcp_env_config = RootMCPConfig.default()

    async def get_user(self, username: str):
        """
        Retrieve a user document by username.

        Args:
            username (str): The username to search for.

        Returns:
            dict: The user document if found.

        Raises:
            HTTPException: If the user is not found.
            Exception: For other database errors.
        """
        collection: Collection = self.mongodb['user']
        try:
            user = collection.find_one({"username": username})
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")
            return user
        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error getting user {username}: {e}")
            raise e

    async def set_token(self, username: str, jira_pat_plain: str):
        """
        Encrypt and set the JIRA personal access token for a user.

        Args:
            username (str): The username to update.
            jira_pat_plain (str): The plain JIRA personal access token.

        Returns:
            dict: Success message if the token is updated.

        Raises:
            HTTPException: If the user is not found.
            Exception: For other database or encryption errors.
        """
        collection: Collection = self.mongodb['user']
        try:
            aes_key = self.root_mcp_env_config.mcp_config.jira.token_enc_key.encode(
                'utf8')
            encrypted_token = encrypt(jira_pat_plain, aes_key)
            result = collection.update_one(
                {"username": username},
                {"$set": {"jira_pat": encrypted_token}}
            )
            if result.matched_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="User not found"
                )
            return {"message": "Token updated successfully"}
        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error setting token for user {username}: {e}")
            raise e

    async def get_token(self, username: str):
        """
        Retrieve and decrypt the JIRA personal access token for a user.

        Args:
            username (str): The username to retrieve the token for.

        Returns:
            dict or None: The decrypted JIRA token, or None if not set.

        Raises:
            HTTPException: If the user does not exist.
            Exception: For other database or decryption errors.
        """
        collection: Collection = self.mongodb['user']
        try:
            user = collection.find_one({"username": username})
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="User not exist"
                )
            if "jira_pat" not in user:
                return None
            aes_key = self.root_mcp_env_config.mcp_config.jira.token_enc_key.encode(
                'utf8')
            decrypted_token = decrypt(user["jira_pat"], aes_key)
            return {"jira_pat": decrypted_token}
        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error getting token for user {username}: {e}")
            raise e


UserServiceDep = Annotated[UserService, Depends(UserService)]
