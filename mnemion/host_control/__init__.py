"""Explicit host authority independent of memory accounts and API availability."""


class HostControlError(ValueError):
    """A fixed, public operation error; credentials and submitted values stay private."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
