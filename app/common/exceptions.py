"""
Base exceptions for the application (optional).
"""


class AppException(Exception):
    """Base application exception."""

    pass


class NotFoundError(AppException):
    """Resource not found."""

    pass


class ValidationError(AppException):
    """Validation failed."""

    pass
