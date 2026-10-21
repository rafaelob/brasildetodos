#!/bin/sh
set -eu

name="${BDT_BACKUP_NAME:-bdt-$(date +%Y%m%dT%H%M%S).dump}"
case "$name" in
  */*|.*) echo "invalid_backup_name" >&2; exit 2 ;;
esac
pg_dump -Fc -f "/backups/$name"
printf '%s\n' "$name"
