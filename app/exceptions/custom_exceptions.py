class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, message: str):
        super().__init__(message=message, status_code=404)


class ConflictError(AppError):
    def __init__(self, message: str):
        super().__init__(message=message, status_code=409)


class ServiceUnavailableError(AppError):
    def __init__(self, message: str = "Service is temporarily unavailable"):
        super().__init__(message=message, status_code=503)
