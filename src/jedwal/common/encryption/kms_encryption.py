import base64
import threading

import boto3
from cryptography.fernet import Fernet

from jedwal.common.encryption.types import EncryptionOutput
from jedwal.config import settings


# In-memory cache to store encryption keys
_key_cache = {}
_key_cache_lock = threading.RLock()

DEFAULT_CONTEXT = {"purpose": "data-encryption", "service": "envelope-encryption"}


def _get_kms_client():
    """Get a KMS client."""
    return boto3.client("kms", region_name=settings.aws_region)


def _generate_data_key(context: dict | None = None) -> tuple[str, str]:
    """Generate a new data encryption key (DEK) using KMS."""
    if context is None:
        context = DEFAULT_CONTEXT

    kms_client = _get_kms_client()
    response = kms_client.generate_data_key(
        KeyId=settings.encryption_key_id,
        KeySpec="AES_256",
        EncryptionContext=context,
    )

    plaintext_key = response["Plaintext"]
    encrypted_key = response["CiphertextBlob"]

    fernet_key = base64.urlsafe_b64encode(plaintext_key).decode("utf-8")
    encrypted_key_b64 = base64.b64encode(encrypted_key).decode("utf-8")

    return fernet_key, encrypted_key_b64


def _decrypt_data_key(encrypted_key_b64: str, context: dict | None = None) -> str:
    """Decrypt an encrypted data key using KMS."""
    if context is None:
        context = DEFAULT_CONTEXT

    encrypted_key = base64.b64decode(encrypted_key_b64)

    kms_client = _get_kms_client()
    response = kms_client.decrypt(
        CiphertextBlob=encrypted_key, EncryptionContext=context
    )

    plaintext_key = response["Plaintext"]
    fernet_key = base64.urlsafe_b64encode(plaintext_key).decode("utf-8")

    return fernet_key


def encrypt(plaintext: str, context: dict | None = None) -> EncryptionOutput:
    """Encrypt data using envelope encryption with KMS."""
    plaintext_key, encrypted_key = _generate_data_key(context)

    f = Fernet(plaintext_key)
    encrypted_data = f.encrypt(plaintext.encode("utf-8"))
    encrypted_data_b64 = base64.b64encode(encrypted_data).decode("utf-8")

    return EncryptionOutput(
        encrypted_data=encrypted_data_b64,
        encrypted_key=encrypted_key,
        context=context or DEFAULT_CONTEXT,
    )


def decrypt(
    encrypted_data_b64: str, encrypted_key_b64: str, context: dict | None = None
) -> str:
    """Decrypt data using envelope encryption with KMS."""
    cache_key = f"{encrypted_key_b64}:{hash(str(context))}"

    with _key_cache_lock:
        plaintext_key = _key_cache.get(cache_key)

    if plaintext_key is None:
        plaintext_key = _decrypt_data_key(encrypted_key_b64, context)
        with _key_cache_lock:
            _key_cache[cache_key] = plaintext_key

    encrypted_data = base64.b64decode(encrypted_data_b64)
    f = Fernet(plaintext_key)
    decrypted_data = f.decrypt(encrypted_data)
    return decrypted_data.decode("utf-8")
