"""Idempotent: create snaptrash schema + all Delta tables. Run once after .env is filled."""
from __future__ import annotations
from snaptrash_common.databricks_client import execute
from snaptrash_common.tables import ddl_create_schema, ALL_DDL
from snaptrash_common.env import settings


def main():
    print(f"target: {settings.fq_schema} (warehouse {settings.DATABRICKS_WAREHOUSE_ID})")
    execute(ddl_create_schema())
    print(f"✅ schema {settings.fq_schema}")
    for ddl_fn in ALL_DDL:
        sql = ddl_fn()
        execute(sql)
        first_line = " ".join(sql.split())[:80]
        print(f"✅ {first_line}...")
    print("done.")


if __name__ == "__main__":
    main()
