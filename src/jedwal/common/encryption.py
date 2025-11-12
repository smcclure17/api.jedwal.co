import base64
import threading
from typing import Any

import boto3
from cryptography.fernet import Fernet
from pydantic import BaseModel

from jedwal.config import settings


class EncryptionOutput(BaseModel):
    """Result of an encryption call"""

    encrypted_data: str
    encrypted_key: str
    context: dict[str, Any]


# In-memory cache to store encryption keys
# TODO: Use e.g. Redis to distribute this across Lambda runtimes
_key_cache = {}
_key_cache_lock = threading.RLock()  # For thread safety

DEFAULT_CONTEXT = {"purpose": "data-encryption", "service": "envelope-encryption"}


class EnvelopeEncryption:
    """Implementation of envelope encryption with AWS KMS."""

    @staticmethod
    def get_kms_client():
        """Get a KMS client."""
        return boto3.client("kms", region_name=settings.aws_region)

    @staticmethod
    def generate_data_key(context: dict | None = None) -> tuple[str, str]:
        """
        Generate a new data encryption key (DEK) using KMS.

        Args:
            context: Optional encryption context

        Returns:
            Tuple containing:
                - The plaintext key formatted for Fernet (base64 urlsafe encoded)
                - The encrypted key (base64 encoded)
        """
        if context is None:
            context = DEFAULT_CONTEXT

        # Generate a data key using KMS
        kms_client = EnvelopeEncryption.get_kms_client()
        response = kms_client.generate_data_key(
            KeyId=settings.encryption_key_id,
            KeySpec="AES_256",
            EncryptionContext=context,
        )

        # Extract the plaintext and encrypted versions of the key
        plaintext_key = response["Plaintext"]
        encrypted_key = response["CiphertextBlob"]

        # Format the plaintext key for Fernet
        fernet_key = base64.urlsafe_b64encode(plaintext_key).decode("utf-8")

        # Base64 encode the encrypted key for storage/transmission
        encrypted_key_b64 = base64.b64encode(encrypted_key).decode("utf-8")

        return fernet_key, encrypted_key_b64

    @staticmethod
    def decrypt_data_key(encrypted_key_b64: str, context: dict | None = None) -> str:
        """
        Decrypt an encrypted data key using KMS.

        Args:
            encrypted_key_b64: Base64 encoded encrypted key
            context: The encryption context that was used during key generation

        Returns:
            The plaintext key formatted for Fernet
        """
        # Default context if none provided
        if context is None:
            context = DEFAULT_CONTEXT

        # Decode the base64 encrypted key
        encrypted_key = base64.b64decode(encrypted_key_b64)

        # Decrypt the key using KMS
        kms_client = EnvelopeEncryption.get_kms_client()
        response = kms_client.decrypt(
            CiphertextBlob=encrypted_key, EncryptionContext=context
        )

        # Format the decrypted key for Fernet
        plaintext_key = response["Plaintext"]
        fernet_key = base64.urlsafe_b64encode(plaintext_key).decode("utf-8")

        return fernet_key

    @staticmethod
    def encrypt(plaintext: str, context: dict | None = None) -> EncryptionOutput:
        """Encrypt data using envelope encryption."""
        # Generate a new data key
        plaintext_key, encrypted_key = EnvelopeEncryption.generate_data_key(context)

        # Encrypt the data using Fernet with the plaintext key, then encode
        f = Fernet(plaintext_key)
        encrypted_data = f.encrypt(plaintext.encode("utf-8"))
        encrypted_data_b64 = base64.b64encode(encrypted_data).decode("utf-8")

        return EncryptionOutput(
            encrypted_data=encrypted_data_b64,
            encrypted_key=encrypted_key,
            context=context or DEFAULT_CONTEXT,
        )

    @staticmethod
    def decrypt(
        encrypted_data_b64: str, encrypted_key_b64: str, context: dict | None = None
    ) -> str:
        """Decrypt data using envelope encryption.

        Args:
            encrypted_data_b64: Base64 encoded encrypted data
            encrypted_key_b64: Base64 encoded encrypted key
            context: The encryption context used during encryption

        Returns:
            The decrypted plaintext
        """
        cache_key = f"{encrypted_key_b64}:{hash(str(context))}"

        # Check in-memory cache
        with _key_cache_lock:
            plaintext_key = _key_cache.get(cache_key)

        # If not in cache, decrypt and cache it
        if plaintext_key is None:
            plaintext_key = EnvelopeEncryption.decrypt_data_key(
                encrypted_key_b64, context
            )
            with _key_cache_lock:
                _key_cache[cache_key] = plaintext_key

        # Decode and decrypt the base64 encrypted data
        encrypted_data = base64.b64decode(encrypted_data_b64)
        f = Fernet(plaintext_key)
        decrypted_data = f.decrypt(encrypted_data)
        return decrypted_data.decode("utf-8")
