#!/usr/bin/env bash
set -euo pipefail
umask 077
mkdir -p backups
backup="backups/agentguard-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
partial="$backup.partial"
trap 'rm -f "$partial"' EXIT
docker compose --env-file .env.deploy exec -T db pg_dump -U agentguard -d agentguard -Fc > "$partial"
test -s "$partial"
mv "$partial" "$backup"
printf 'Backup saved: %s\n' "$backup"
