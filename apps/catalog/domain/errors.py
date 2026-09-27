class CategoryNameExistsError(Exception):
    pass


class BarcodeExistsError(Exception):
    """Another live product already uses the barcode."""
