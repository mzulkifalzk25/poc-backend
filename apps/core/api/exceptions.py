from rest_framework.exceptions import APIException


class ApiError(APIException):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        fields: dict | None = None,
        retry_after: int | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.fields = fields or {}
        self.retry_after = retry_after
        super().__init__(detail=message, code=code)
