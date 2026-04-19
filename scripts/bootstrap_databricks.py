"""Idempotent: create snaptrash schema + all Delta tables. Run once after .env is filled.

Run with: uv run --project apps/ingestion python scripts/bootstrap_databricks.py
"""
from __future__ import annotations
from snaptrash_common.databricks_client import execute
from snaptrash_common.tables import ddl_create_schema, ALL_DDL, SCANS, INSIGHTS
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
    
    # Schema evolution for sustainability fields (idempotent for existing tables)
    for table_name, columns in [
        (SCANS, "total_plastic_kg DOUBLE, ban_flag_count INT, recyclable_count INT"),
        (INSIGHTS, "sustainability_score DOUBLE, badge_tier STRING, score_feedback_message STRING"),
    ]:
        try:
            alter_sql = f"ALTER TABLE {table_name} ADD COLUMNS ({columns})"
            execute(alter_sql)
            print(f"✅ added sustainability columns to {table_name}")
        except Exception as e:
            err_str = str(e).lower()
            if any(phrase in err_str for phrase in ["already exists", "duplicate column", "no such table"]):
                print(f"✅ sustainability columns already exist or table not ready in {table_name}")
            else:
                print(f"⚠️  ALTER for {table_name} note: {type(e).__name__}: {e}")
    
    print("✅ bootstrap completed (tables + schema evolution)")
    print("done.")


if __name__ == "__main__":
    main()
