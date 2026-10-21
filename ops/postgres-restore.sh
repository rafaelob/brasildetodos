#!/bin/sh
set -eu

backup="${BDT_RESTORE_BACKUP:?BDT_RESTORE_BACKUP is required}"
database="${BDT_RESTORE_DB:-bdt_restore}"
case "$backup" in
  */*|.*) echo "invalid_backup_name" >&2; exit 2 ;;
esac
case "$database" in
  *[!a-z0-9_]*|'') echo "invalid_restore_database" >&2; exit 2 ;;
esac
case "$database" in
  postgres|template0|template1) echo "protected_restore_database" >&2; exit 2 ;;
esac

export PGHOST=postgres PGUSER=bdt_admin PGDATABASE=postgres
if psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$database'" | grep -q 1; then
  echo "restore_destination_exists" >&2
  exit 3
fi
createdb -O bdt_app "$database"
pg_restore --no-owner --no-privileges --role=bdt_app -d "$database" "/backups/$backup"
PGUSER=bdt_app PGDATABASE="$database" psql -v ON_ERROR_STOP=1 \
  -c "select version_num from alembic_version" \
  -c "select count(*) from information_schema.tables where table_schema='public'"
