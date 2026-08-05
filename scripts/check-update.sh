#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/proxmox-pbs-dashboard
LOCK_FILE=/run/lock/proxmox-pbs-dashboard-update.lock

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root." >&2
  exit 1
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Outra verificação ou atualização já está em execução."
  exit 0
fi

cd "$APP_DIR"

BRANCH=$(git branch --show-current)
if [[ "$BRANCH" != "main" ]]; then
  echo "Atualização ignorada: branch atual é '$BRANCH', esperado 'main'."
  exit 0
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Atualização ignorada: existem alterações locais no repositório."
  exit 0
fi

git fetch --quiet origin main

LOCAL_SHA=$(git rev-parse HEAD)
REMOTE_SHA=$(git rev-parse origin/main)

if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
  echo "Nenhuma atualização disponível."
  exit 0
fi

if ! git merge-base --is-ancestor "$LOCAL_SHA" "$REMOTE_SHA"; then
  echo "Atualização ignorada: a cópia local divergiu de origin/main." >&2
  exit 1
fi

echo "Nova versão encontrada: $LOCAL_SHA -> $REMOTE_SHA"
exec "$APP_DIR/scripts/update.sh"
