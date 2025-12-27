"""Custom exceptions."""

from fastapi import HTTPException, status


class NotFoundException(HTTPException):
    """Resource not found exception."""

    def __init__(self, detail=None):
        if detail is None:
            detail = [{"msg": "Resource not found"}]
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class BadRequestException(HTTPException):
    """Bad request exception."""

    def __init__(self, detail: str | list = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class UnauthorizedException(HTTPException):
    """Unauthorized exception."""

    def __init__(self, detail="Unauthorized"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class ForbiddenException(HTTPException):
    """Forbidden exception."""

    def __init__(self, detail: str = "Forbidden"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class ConflictException(HTTPException):
    """Conflict exception."""

    def __init__(self, detail=None):
        if detail is None:
            detail = [{"msg": "Resource already exist"}]
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class QuotaExceededException(HTTPException):
    """Account exceeded allowed quota exception"""

    def __init__(self, detail: str = "Quota exceeded"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class UnsupportedMediaTypeException(HTTPException):
    def __init__(self, detail: str | list = "Unsupported media type"):
        super().__init__(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=detail
        )


class UnprocessableContentException(HTTPException):
    def __init__(self, detail: str | list = "Unsupported media type"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail
        )
