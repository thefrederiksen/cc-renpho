"""Errors, each mapped to a distinct process exit code.

An agent driving this tool branches on the exit code, so the codes are part of
the contract and do not change without a major version bump.
"""


class CcRenphoError(Exception):
    """Base class. Every failure this tool raises carries an exit code."""

    exit_code = 1


class ConfigError(CcRenphoError):
    """Missing or malformed configuration - credentials, paths, arguments."""

    exit_code = 2


class AuthError(CcRenphoError):
    """Renpho rejected the credentials."""

    exit_code = 3


class ApiError(CcRenphoError):
    """Renpho accepted the credentials but the request failed."""

    exit_code = 4


class IncompleteDownloadError(CcRenphoError):
    """Fewer records came back than the server says it holds."""

    exit_code = 5
