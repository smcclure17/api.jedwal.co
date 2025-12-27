from jedwal.common.encryption.types import EncryptionOutput

DEFAULT_CONTEXT = {"purpose": "data-encryption", "service": "pass-through-encryption"}


def encrypt(*, plaintext: str, context: dict | None = None) -> EncryptionOutput:
    """No-op encryption for testing."""
    return EncryptionOutput(
        encrypted_data=plaintext,
        encrypted_key="fake-key",
        context=context or DEFAULT_CONTEXT,
    )


def decrypt(
    *, encrypted_data: str, encrypted_key: str, context: dict | None = None
) -> str:
    """No-op decryption for testing."""
    return encrypted_data
