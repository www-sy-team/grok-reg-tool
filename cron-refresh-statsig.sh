#!/bin/bash
# Refresh x-statsig-id for grok2api (executes inside grok-reg-tool container)
LOG=/var/log/statsig-refresh.log
echo "[$(date)] Starting statsig refresh..." >> "$LOG"
docker exec -e http_proxy="http://host.docker.internal:10803" \
  -e https_proxy="http://host.docker.internal:10803" \
  -e NO_PROXY="127.0.0.1,localhost,::1" \
  grok-reg-tool timeout 150 python3 /app/register/refresh_statsig_id.py \
  2>&1 | grep -v "dbus\|gcm\|google_apis\|Deprecat\|Extension\|devtools\|DevTools listening" >> "$LOG"
echo "[$(date)] Done." >> "$LOG"
