from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from jedwal.config import settings
from jedwal.common.encryption import kms_encryption, pass_through_encryption
from jedwal.common.encryption.types import DecryptFn, EncryptFn


@dataclass(frozen=True)
class EncryptionService:
    """Bundle of encryption functions"""

    encrypt: EncryptFn
    decrypt: DecryptFn


def get_encryption_service() -> EncryptionService:
    """Get the appropriate encryption service based on settings."""
    if settings.enable_encryption:
        return EncryptionService(
            encrypt=kms_encryption.encrypt, decrypt=kms_encryption.decrypt
        )
    return EncryptionService(
        encrypt=pass_through_encryption.encrypt, decrypt=pass_through_encryption.decrypt
    )


Encryption = Annotated[EncryptionService, Depends(get_encryption_service)]
