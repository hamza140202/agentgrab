"""Errors. MethodError is the contract: one line, root cause only."""
from __future__ import annotations


class AgentGrabError(Exception):
    """Base class for all AgentGrab errors."""


class MethodError(AgentGrabError):
    """A download method failed. Message MUST be a single-line root cause."""


class VerificationError(AgentGrabError):
    """Downloaded file failed ffprobe verification."""


class PlatformNotFound(AgentGrabError):
    """URL does not match any supported platform."""
