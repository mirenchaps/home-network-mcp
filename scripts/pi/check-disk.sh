#!/bin/bash
#
# check-disk.sh
#
# Reports disk usage for real mounted filesystems on the Pi.
#
# Usage: ./check-disk.sh [warn_threshold_percent_free]
# Default warning threshold: 15% free

set -euo pipefail

WARN_THRESHOLD="${1:-15}"

HOSTNAME_VAL=$(hostname)
CHECKED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# -x excludes pseudo/virtual filesystems (tmpfs, devtmpfs, overlay, etc.)
# -P gives POSIX-stable single-line-per-mount output, easier to parse
VOLUMES_JSON=""
FIRST=true

while read -r FILESYSTEM SIZE USED AVAIL PCT_USED MOUNT; do
    # skip header row and pseudo filesystems
    case "$FILESYSTEM" in
        Filesystem|tmpfs|devtmpfs|overlay|udev) continue ;;
    esac

    PCT_USED_NUM="${PCT_USED%\%}"
    PCT_FREE=$((100 - PCT_USED_NUM))
    WARNING="false"
    if [ "$PCT_FREE" -lt "$WARN_THRESHOLD" ]; then
        WARNING="true"
    fi

    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        VOLUMES_JSON="${VOLUMES_JSON},"
    fi

    VOLUMES_JSON="${VOLUMES_JSON}
    {
      \"filesystem\": \"$FILESYSTEM\",
      \"mount\": \"$MOUNT\",
      \"size\": \"$SIZE\",
      \"used\": \"$USED\",
      \"available\": \"$AVAIL\",
      \"percent_free\": $PCT_FREE,
      \"warning\": $WARNING
    }"
done < <(df -hPx tmpfs -x devtmpfs -x overlay -x squashfs 2>/dev/null)

cat <<EOF
{
  "host": "$HOSTNAME_VAL",
  "checked_at": "$CHECKED_AT",
  "volumes": [$VOLUMES_JSON
  ]
}
EOF
