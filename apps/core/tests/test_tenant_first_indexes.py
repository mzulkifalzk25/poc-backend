import pytest
from django.db import connection

# Global by design: the public activation code and the opaque device token
# find their tenant; the contract lists the live-PC index on counter_id alone
# and a GIN trigram index on name_lc (a GIN trigram index cannot lead with a
# bigint without the btree_gin extension).
GLOBAL_BY_DESIGN = {
    "uniq_device_code_hash",
    "uniq_device_token_hash",
    "uniq_device_live_per_counter",
    "product_name_trgm_idx",
}
APP_TABLE_PREFIXES = ("accounts_", "audit_", "catalog_", "inventory_", "shifts_", "tenants_")

_INDEXES_SQL = """
SELECT i.relname, t.relname, first_col.attname
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class t ON t.oid = ix.indrelid
LEFT JOIN pg_attribute first_col
  ON first_col.attrelid = t.oid AND first_col.attnum = ix.indkey[0]
WHERE NOT ix.indisprimary
  AND EXISTS (
    SELECT 1 FROM pg_attribute a
    WHERE a.attrelid = t.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
  )
"""


@pytest.mark.django_db
def test_every_index_on_a_tenant_table_starts_with_tenant_id():
    with connection.cursor() as cursor:
        cursor.execute(_INDEXES_SQL)
        rows = [row for row in cursor.fetchall() if row[1].startswith(APP_TABLE_PREFIXES)]

    offenders = [
        f"{table}.{index} starts with {first or 'an expression'}"
        for index, table, first in rows
        if first != "tenant_id" and index not in GLOBAL_BY_DESIGN
    ]
    assert rows
    assert offenders == []


@pytest.mark.django_db
def test_the_global_indexes_still_exist():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE indexname = ANY(%s)", [list(GLOBAL_BY_DESIGN)]
        )
        names = {row[0] for row in cursor.fetchall()}

    assert names == GLOBAL_BY_DESIGN
