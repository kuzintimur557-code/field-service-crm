#!/bin/bash
# Persistent dev tunnel: exposes local CRM (port 8000) via localhost.run.
# Restarts the SSH tunnel automatically while the script runs.
set -u

LOG=/tmp/crm_tunnel.log
echo "$(date '+%F %T') tunnel watchdog started" >> "$LOG"

while true; do
    ssh -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=20 \
        -o ServerAliveCountMax=3 \
        -o ExitOnForwardFailure=yes \
        -R 80:127.0.0.1:8000 nokey@localhost.run >> "$LOG" 2>&1
    echo "$(date '+%F %T') tunnel dropped, restarting in 5s" >> "$LOG"
    sleep 5
done
