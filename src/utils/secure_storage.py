"""Secure storage for API keys using OS keyring."""
from typing import Optional

import keyring
from keyring.errors import PasswordSetError
from loguru import logger

# Keyring service and account names
SERVICE_NAME = "nvidia_ai_agent"
API_KEY_ACCOUNT = "api_key"
GOOGLE_API_KEY_ACCOUNT = "google_api_key"


class SecureStorage:
    """Secure storage for sensitive data using OS keyring."""

    @staticmethod
    def store_api_key(api_key: str) -> bool:
        """Store NVIDIA API key securely.

        Args:
            api_key: The API key to store

        Returns:
            True if successful, False otherwise
        """
        try:
            keyring.set_password(SERVICE_NAME, API_KEY_ACCOUNT, api_key)
            logger.info("API key stored securely")
            return True
        except PasswordSetError as e:
            logger.error(f"Failed to store API key: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error storing API key: {e}")
            return False

    @staticmethod
    def get_api_key() -> Optional[str]:
        """Retrieve NVIDIA API key from secure storage.

        Returns:
            The stored API key or None if not found
        """
        try:
            key = keyring.get_password(SERVICE_NAME, API_KEY_ACCOUNT)
            if key:
                logger.debug("API key retrieved from secure storage")
            return key
        except Exception as e:
            logger.error(f"Failed to retrieve API key: {e}")
            return None

    @staticmethod
    def delete_api_key() -> bool:
        """Delete stored NVIDIA API key.

        Returns:
            True if successful, False otherwise
        """
        try:
            keyring.delete_password(SERVICE_NAME, API_KEY_ACCOUNT)
            logger.info("API key deleted from secure storage")
            return True
        except Exception as e:
            logger.error(f"Failed to delete API key: {e}")
            return False

    @staticmethod
    def has_api_key() -> bool:
        """Check if an API key is stored.

        Returns:
            True if API key exists, False otherwise
        """
        return SecureStorage.get_api_key() is not None

    # --- Google API Key (for Gemini Live) ---

    @staticmethod
    def store_google_api_key(api_key: str) -> bool:
        """Store Google API key securely.

        Args:
            api_key: The API key to store

        Returns:
            True if successful, False otherwise
        """
        try:
            keyring.set_password(SERVICE_NAME, GOOGLE_API_KEY_ACCOUNT, api_key)
            logger.info("Google API key stored securely")
            return True
        except PasswordSetError as e:
            logger.error(f"Failed to store Google API key: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error storing Google API key: {e}")
            return False

    @staticmethod
    def get_google_api_key() -> Optional[str]:
        """Retrieve Google API key from secure storage.

        Returns:
            The stored API key or None if not found
        """
        try:
            key = keyring.get_password(SERVICE_NAME, GOOGLE_API_KEY_ACCOUNT)
            if key:
                logger.debug("Google API key retrieved from secure storage")
            return key
        except Exception as e:
            logger.error(f"Failed to retrieve Google API key: {e}")
            return None

    @staticmethod
    def delete_google_api_key() -> bool:
        """Delete stored Google API key.

        Returns:
            True if successful, False otherwise
        """
        try:
            keyring.delete_password(SERVICE_NAME, GOOGLE_API_KEY_ACCOUNT)
            logger.info("Google API key deleted from secure storage")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Google API key: {e}")
            return False


# Convenience functions
def store_api_key(api_key: str) -> bool:
    """Store NVIDIA API key securely."""
    return SecureStorage.store_api_key(api_key)


def get_api_key() -> Optional[str]:
    """Retrieve NVIDIA API key from secure storage."""
    return SecureStorage.get_api_key()


def delete_api_key() -> bool:
    """Delete stored NVIDIA API key."""
    return SecureStorage.delete_api_key()


def has_api_key() -> bool:
    """Check if an API key is stored."""
    return SecureStorage.has_api_key()


def store_google_api_key(api_key: str) -> bool:
    """Store Google API key securely."""
    return SecureStorage.store_google_api_key(api_key)


def get_google_api_key() -> Optional[str]:
    """Retrieve Google API key from secure storage."""
    return SecureStorage.get_google_api_key()


def delete_google_api_key() -> bool:
    """Delete stored Google API key."""
    return SecureStorage.delete_google_api_key()
