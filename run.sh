#!/usr/bin/env bash
# Founder Intelligence Agent - one-command setup and run.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "==> creating virtualenv"
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi

case "${1:-serve}" in
  serve) exec .venv/bin/python -m founder_agent.cli serve "${@:2}" ;;
  demo)  exec .venv/bin/python -m founder_agent.cli demo ;;
  test)  exec .venv/bin/python -m pytest tests -q ;;
  *)     exec .venv/bin/python -m founder_agent.cli "$@" ;;
esac
