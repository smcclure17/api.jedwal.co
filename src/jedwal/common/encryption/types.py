"""Shared types for encryption module."""

from typing import Any, Protocol

from pydantic import BaseModel


class EncryptionOutput(BaseModel):
    """Result of an encryption call"""

    encrypted_data: str
    encrypted_key: str
    context: dict[str, Any]


class EncryptFn(Protocol):
    def __call__(
        self, *, plaintext: str, context: dict | None = None
    ) -> EncryptionOutput: ...


class DecryptFn(Protocol):
    def __call__(
        self,
        *,
        encrypted_data: str,
        encrypted_key: str,
        context: dict | None = None,
    ) -> str: ...
