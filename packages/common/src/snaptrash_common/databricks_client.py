from __future__ import annotations
import os
import time
from typing import Any
from .env import settings

_client = None  # WorkspaceClient, lazy
_spark = None  # pyspark.sql.SparkSession, lazy


def _get_spark():
    """
    Return an active SparkSession if one is available (i.e., we're inside
    Databricks notebook/serverless compute). Returns None on local dev.
    Caches the result after first call.
    """
    global _spark
    if _spark is not None:
        return _spark
    try:
        from pyspark.sql import SparkSession  # type: ignore
        sess = SparkSession.getActiveSession()
        if sess is not None:
            _spark = sess
            return _spark
        # No active session — try builder (works on some cluster configs)
        sess = SparkSession.builder.getOrCreate()
        if sess is not None:
            _spark = sess
            return _spark
    except Exception:
        pass
    return None


def _in_databricks_runtime() -> bool:
    """True if a SparkSession is available (works for both cluster and serverless)."""
    return _get_spark() is not None


def client():
    global _client
    if _client is None:
        from databricks.sdk import WorkspaceClient
        if _in_databricks_runtime():
            _client = WorkspaceClient()  # auto-auth from notebook context
        else:
            if not settings.DATABRICKS_HOST or not settings.DATABRICKS_TOKEN:
                raise RuntimeError("DATABRICKS_HOST and DATABRICKS_TOKEN must be set in .env")
            _client = WorkspaceClient(
                host=settings.DATABRICKS_HOST,
                token=settings.DATABRICKS_TOKEN,
            )
    return _client


def _to_params(parameters: dict[str, Any] | None):
    from databricks.sdk.service.sql import StatementParameterListItem
    if not parameters:
        return None
    out = []
    for k, v in parameters.items():
        if v is None:
            out.append(StatementParameterListItem(name=k, value=None, type="STRING"))
        elif isinstance(v, bool):
            out.append(StatementParameterListItem(name=k, value=str(v).lower(), type="BOOLEAN"))
        elif isinstance(v, int):
            out.append(StatementParameterListItem(name=k, value=str(v), type="BIGINT"))
        elif isinstance(v, float):
            out.append(StatementParameterListItem(name=k, value=str(v), type="DOUBLE"))
        else:
            out.append(StatementParameterListItem(name=k, value=str(v), type="STRING"))
    return out


class _Col:
    __slots__ = ("name",)
    def __init__(self, name: str):
        self.name = name


class _Schema:
    def __init__(self, cols: list[str]):
        self.columns = [_Col(c) for c in cols]


class _Manifest:
    def __init__(self, cols: list[str]):
        self.schema = _Schema(cols)


class _SparkResult:
    """Minimal shim matching the shape used by callers of execute()."""
    def __init__(self, rows: list[dict] | None, columns: list[str] | None):
        self._rows = rows or []
        self._cols = columns or []
        self.data_array = [[r.get(c) for c in self._cols] for r in self._rows]
        self.manifest = _Manifest(self._cols)

    @property
    def result(self):
        return self if self._rows else None


_ISO_TS_RE = None


def _looks_like_ts(v: str) -> bool:
    """True if string looks like an ISO 8601 timestamp (contains 'T' or date+time separator)."""
    global _ISO_TS_RE
    if _ISO_TS_RE is None:
        import re
        _ISO_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
    return bool(_ISO_TS_RE.match(str(v)))


def _ts_lit(v: str) -> str:
    """
    Convert an ISO timestamp string to a Spark-compatible TIMESTAMP literal.
    Spark SQL accepts 'yyyy-MM-dd HH:mm:ss[.SSS]' format.
    Strip timezone suffix and replace T separator.
    """
    s = str(v)
    # Strip timezone offset (+HH:MM or Z)
    for sep in ("+", "-"):
        idx = s.rfind(sep)
        if idx > 10:  # found after the date part
            s = s[:idx]
            break
    if "Z" in s:
        s = s.replace("Z", "")
    # Replace T with space
    s = s.replace("T", " ")
    # Ensure no trailing space or extra chars
    return f"TIMESTAMP '{s.strip()}'"


def _execute_spark(sql: str, parameters: dict[str, Any] | None):
    spark = _get_spark()
    if spark is None:
        return None
    # Parameter substitution for :name placeholders — longest keys first to
    # avoid `:ts` clobbering `:ts_something`.
    if parameters:
        for k in sorted(parameters.keys(), key=len, reverse=True):
            v = parameters[k]
            if v is None:
                lit = "NULL"
            elif isinstance(v, bool):
                lit = "TRUE" if v else "FALSE"
            elif isinstance(v, (int, float)):
                lit = str(v)
            else:
                sv = str(v)
                if _looks_like_ts(sv):
                    # Use TIMESTAMP literal so Spark doesn't need implicit cast
                    lit = _ts_lit(sv)
                else:
                    lit = "'" + sv.replace("'", "''") + "'"
            sql = sql.replace(f":{k}", lit)
    df = spark.sql(sql)
    cols = df.columns
    # collect() triggers DML/DDL execution — let errors propagate so callers see them
    rows = [r.asDict(recursive=True) for r in df.collect()]
    return _SparkResult(rows, cols)


def execute(
    sql: str,
    parameters: dict[str, Any] | None = None,
    *,
    warehouse_id: str | None = None,
    timeout_s: int = 300,
):
    # Inside Databricks notebooks/jobs prefer spark.sql — no warehouse needed.
    if _in_databricks_runtime():
        res = _execute_spark(sql, parameters)
        if res is not None:
            return res

    from databricks.sdk.service.sql import StatementState
    if not settings.DATABRICKS_WAREHOUSE_ID and not warehouse_id:
        raise RuntimeError("DATABRICKS_WAREHOUSE_ID must be set in .env")

    resp = client().statement_execution.execute_statement(
        warehouse_id=warehouse_id or settings.DATABRICKS_WAREHOUSE_ID,
        statement=sql,
        parameters=_to_params(parameters),
        wait_timeout="30s",
    )

    deadline = time.time() + timeout_s
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        if time.time() > deadline:
            raise TimeoutError(f"Statement {resp.statement_id} exceeded {timeout_s}s")
        time.sleep(1)
        resp = client().statement_execution.get_statement(resp.statement_id)

    if resp.status.state != StatementState.SUCCEEDED:
        err = resp.status.error
        raise RuntimeError(f"SQL failed ({resp.status.state}): {err.message if err else 'unknown'}")

    return resp


def fetch_all(sql: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    resp = execute(sql, parameters)
    if not resp.result or not resp.result.data_array:
        return []
    cols = [c.name for c in resp.manifest.schema.columns]
    return [dict(zip(cols, row)) for row in resp.result.data_array]
