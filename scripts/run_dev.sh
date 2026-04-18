#!/usr/bin/env bash
# Run all 3 services in parallel. Use tmux/foreman in production.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

echo "→ ingestion API on :8000"
uv run --project apps/ingestion uvicorn snaptrash_ingestion.main:app --reload --port 8000 &
PID_API=$!

echo "→ frontend on :5173"
( cd apps/frontend && pnpm dev ) &
PID_FE=$!

trap "kill $PID_API $PID_FE 2>/dev/null || true" EXIT
wait
