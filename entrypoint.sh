#!/bin/bash
# entrypoint.sh
#
# Runs as root briefly to fix SSH key permissions, then drops to the non-root
# 'mcp' user before starting the exporter. Docker volume mounts are 644 by
# default; SSH refuses private keys that are world-readable.
#
# The key is copied to /tmp so the mcp user can own it — the original mount
# is read-only and owned by root.

if [ -f /app/id_ed25519 ]; then
    cp /app/id_ed25519 /tmp/id_ed25519
    chmod 600 /tmp/id_ed25519
    chown mcp /tmp/id_ed25519
fi

exec su -s /bin/bash mcp -c "python /app/exporter.py"

