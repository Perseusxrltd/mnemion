"""Bounded capture errors, usable without loading the encryption runtime."""


class InboxError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
