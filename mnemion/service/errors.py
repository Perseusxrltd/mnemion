"""Stable, non-secret error responses for every service transport."""


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def not_found() -> ServiceError:
    # Deliberately identical for absent and inaccessible resource identifiers.
    return ServiceError(404, "not_found", "The resource is unavailable.")


def forbidden() -> ServiceError:
    return ServiceError(403, "forbidden", "This action requires additional access.")
