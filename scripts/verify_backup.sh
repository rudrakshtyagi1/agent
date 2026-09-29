#!/usr/bin/env bash
# Restore into a temporary database. Never overwrite the live database.
set -euo pipefail
[[ $# == 1 && -f "$1" ]] || { echo 'Usage: scripts/verify_backup.sh backups/file.dump' >&2; exit 2; }
restore_db="verify_$(date -u +%Y%m%d%H%M%S)_$$"
compose=(docker compose --env-file .env.deploy)
"${compose[@]}" exec -T db createdb -U agentguard "$restore_db"
trap '"${compose[@]}" exec -T db dropdb -U agentguard "$restore_db" >/dev/null' EXIT
"${compose[@]}" exec -T db pg_restore --exit-on-error --no-owner -U agentguard -d "$restore_db" < "$1"
"${compose[@]}" exec -T db psql -U agentguard -d "$restore_db" -v ON_ERROR_STOP=1 -c 'SELECT version_num FROM alembic_version; SELECT COUNT(*) AS restored_traces FROM monitor_traces;'
echo 'Restore verified in an isolated temporary database.'
