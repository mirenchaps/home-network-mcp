#!/bin/bash
#
# check-uptime.sh
#
# Reports system uptime and last boot time for the Pi.
#
# Usage: ./check-uptime.sh

set -euo pipefail

HOSTNAME_VAL=$(hostname)
CHECKED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

UPTIME_SECONDS=$(awk '{print int($1)}' /proc/uptime)
UPTIME_DAYS=$(awk -v secs="$UPTIME_SECONDS" 'BEGIN { printf "%.2f", secs / 86400 }')

DAYS=$((UPTIME_SECONDS / 86400))
HOURS=$(((UPTIME_SECONDS % 86400) / 3600))
MINUTES=$(((UPTIME_SECONDS % 3600) / 60))
UPTIME_READABLE="${DAYS}d ${HOURS}h ${MINUTES}m"

LAST_BOOT=$(date -u -d "@$(($(date +%s) - UPTIME_SECONDS))" +"%Y-%m-%dT%H:%M:%SZ")

cat <<EOF
{
  "host": "$HOSTNAME_VAL",
  "checked_at": "$CHECKED_AT",
  "last_boot": "$LAST_BOOT",
  "uptime_days": $UPTIME_DAYS,
  "uptime_readable": "$UPTIME_READABLE"
}
EOF
