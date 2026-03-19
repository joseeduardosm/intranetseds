#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/jesmartins/intranet"
BACKUP_DIR="${PROJECT_DIR}/backups"
DB_NAME="intranet"
MYSQL_CNF="${MYSQL_CNF:-/root/.my.cnf}"
RETENTION_DAYS=30

mkdir -p "${BACKUP_DIR}"

if [[ ! -r "${MYSQL_CNF}" ]]; then
  echo "Arquivo de credenciais nao legivel: ${MYSQL_CNF}" >&2
  exit 1
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_FILE="${BACKUP_DIR}/backup_intranet_${TIMESTAMP}.sql.gz"

mysqldump --defaults-extra-file="${MYSQL_CNF}" "${DB_NAME}" | gzip > "${OUTPUT_FILE}"

# Remove backups antigos
find "${BACKUP_DIR}" -type f -name "backup_intranet_*.sql.gz" -mtime +${RETENTION_DAYS} -delete

echo "Backup concluido: ${OUTPUT_FILE}"
