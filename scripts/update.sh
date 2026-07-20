#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/update.sh" >&2
  exit 1
fi

cd /opt/proxmox-pbs-dashboard
git pull --ff-only
.venv/bin/pip install -r requirements.txt
systemctl restart proxmox-pbs-dashboard
systemctl --no-pager --full status proxmox-pbs-dashboard
