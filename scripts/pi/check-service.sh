#!/bin/bash
#
# check-service.sh
#
# Checks the status of a systemd service (e.g. homebridge) and outputs JSON.
# Designed to be run remotely via SSH: the MCP server pipes this script's
# contents into `ssh pi@host bash -s -- <service_name>`.
#
# Usage: ./check-service.sh <service_name>

set -euo pipefail

SERVICE_NAME="${1:?Usage: check-service.sh <service_name>}"

# is-active returns non-zero for inactive services, so don't let set -e kill us
ACTIVE_STATE=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || true)
ENABLED_STATE=$(systemctl is-enabled "$SERVICE_NAME" 2>/dev/null || true)

# Get when the service last started, in ISO-ish format
STARTED_AT=$(systemctl show "$SERVICE_NAME" --property=ActiveEnterTimestamp --value 2>/dev/null || true)

# Basic uptime-since-start in seconds, best effort (falls back to empty if parsing fails)
if [ -n "$STARTED_AT" ] && [ "$STARTED_AT" != "n/a" ]; then
    STARTED_EPOCH=$(date -d "$STARTED_AT" +%s 2>/dev/null || echo "")
    NOW_EPOCH=$(date +%s)
    if [ -n "$STARTED_EPOCH" ]; then
        UPTIME_SECONDS=$((NOW_EPOCH - STARTED_EPOCH))
    else
        UPTIME_SECONDS="null"
    fi
else
    UPTIME_SECONDS="null"
fi

HOSTNAME_VAL=$(hostname)
CHECKED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat <<EOF
{
  "host": "$HOSTNAME_VAL",
  "checked_at": "$CHECKED_AT",
  "service": "$SERVICE_NAME",
  "active_state": "$ACTIVE_STATE",
  "enabled_state": "$ENABLED_STATE",
  "started_at": "$STARTED_AT",
  "uptime_seconds": $UPTIME_SECONDS
}
EOF
