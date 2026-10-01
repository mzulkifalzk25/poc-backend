# Pakistan General Mart POC Dataset

- Categories: **26**
- Products: **379**
- Currency: **PKR**
- Barcodes: **synthetic EAN-13-format; POC only**

## Suggested database design

Use `category_id` -> `product_id`, with `barcode` unique at the product level. Keep mart-specific price and stock in a separate `mart_inventory` table keyed by `mart_id + product_id`.

## Important

Prices, stock quantities, brands and barcodes in this dataset are dummy test values. They are not live retail prices or official GS1/manufacturer barcode assignments.
