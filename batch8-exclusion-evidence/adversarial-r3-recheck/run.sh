#!/bin/sh
# r3b runner: clean env, owned DB URL, repo venv python (read-only use). Usage: run.sh <script> <logname>
cd "$(dirname "$0")"
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
  PYTHONPATH=/Users/roger/.codex/worktrees/afa1/audit_app/backend \
  DATABASE_URL=postgresql+psycopg2://batch7_worker:batch7-inert-local@127.0.0.1:55485/batch7_etl_worker \
  /Users/roger/Documents/projects/audit_app/venv/bin/python "$1" > "$2.log" 2>&1
code=$?
echo "exit=$code" > "$2.exit"
echo "exit=$code"
