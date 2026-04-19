"""Idempotent: create snaptrash schema + all Delta tables (including new EMAIL_ALERTS for SMTP alerts).
Run once after .env is filled and uv sync. Now includes email_alerts DDL via ALL_DDL (per plan).
"""
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
        try:
            execute(sql)
            first_line = " ".join(sql.split())[:80]
            print(f"✅ {first_line}...")
        except Exception as e:
            # ddl_scans_unified (CREATE OR REPLACE VIEW) fails if SYNTH_SCANS not yet seeded.
            # Run scripts/seed_synthetic_scans.py first, then re-run bootstrap to create view.
            first_line = " ".join(sql.split())[:60]
            print(f"⚠️  skipped (run seed first): {first_line}... [{e}]")
    print("done.")


if __name__ == "__main__":
    main()
