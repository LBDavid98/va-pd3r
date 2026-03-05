#!/usr/bin/env bash
# Start both backend API and frontend dev server.
# Usage: ./scripts/dev.sh
#   Ctrl-C stops both.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

FRONTEND_PORT="${FRONTEND_PORT:-5175}"

cleanup() {
  echo ""
  echo "Shutting down..."
  kill $API_PID $VITE_PID 2>/dev/null
  wait $API_PID $VITE_PID 2>/dev/null
  echo "Done."
}
trap cleanup EXIT INT TERM

echo "Starting PD3r backend on :8000 ..."
poetry run pd3r-api &
API_PID=$!

echo "Starting frontend on :${FRONTEND_PORT} ..."
cd frontend && npm run dev -- --port "$FRONTEND_PORT" &
VITE_PID=$!

echo ""
echo "  Backend API:  http://localhost:8000"
echo "  Frontend:     http://localhost:${FRONTEND_PORT}"
echo ""
echo "Press Ctrl-C to stop both."

wait
