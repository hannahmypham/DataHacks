from __future__ import annotations
import time
from typing import Any
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState, StatementParameterListItem
from .env import settings

_client: WorkspaceClient | None = None


def client() -> WorkspaceClient:
    global _client
    if _client is None:
        if not settings.DATABRICKS_HOST or not settings.DATABRICKS_TOKEN:
            raise RuntimeError("DATABRICKS_HOST and DATABRICKS_TOKEN must be set in .env")
        _client = WorkspaceClient(
            host=settings.DATABRICKS_HOST,
            token=settings.DATABRICKS_TOKEN,
        )
    return _client


def _to_params(parameters: dict[str, Any] | None) -> list[StatementParameterListItem] | None:
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


def execute(
    sql: str,
    parameters: dict[str, Any] | None = None,
    *,
    warehouse_id: str | None = None,
    timeout_s: int = 60,
):
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
