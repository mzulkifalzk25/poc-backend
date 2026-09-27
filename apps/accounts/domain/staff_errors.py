class StaffConflictError(Exception):
    """`code` is the API error code; `field_name` the field it belongs to."""

    def __init__(self, code: str, field_name: str):
        super().__init__(code)
        self.code = code
        self.field_name = field_name
