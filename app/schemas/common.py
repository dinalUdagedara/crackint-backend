"""
Common enums and shared Pydantic models for Crackint backend.
"""

from enum import Enum


class RoleLevel(str, Enum):
    """User role / seniority level."""

    INTERN = "INTERN"
    ASE = "ASE"
    SSE = "SSE"
    OTHER = "OTHER"


class SessionMode(str, Enum):
    """Preparation session mode."""

    TARGETED = "TARGETED"
    QUICK_PRACTICE = "QUICK_PRACTICE"
    TUTOR_CHAT = "TUTOR_CHAT"


class SessionStatus(str, Enum):
    """Preparation session lifecycle status."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


class SenderType(str, Enum):
    """Who sent a given message."""

    USER = "USER"
    ASSISTANT = "ASSISTANT"


class MessageType(str, Enum):
    """Semantic type of a message."""

    QUESTION = "QUESTION"
    ANSWER = "ANSWER"
    FEEDBACK = "FEEDBACK"
    COVER_LETTER = "COVER_LETTER"

