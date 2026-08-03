#!/bin/bash
# entrypoint.sh
#
# Shared entrypoint for both the exporter and the MCP server pods.
# Both pods use the same Docker image — this script selects which Python
# process to run based on the first argument:
#
#   /entrypoint.sh exporter   → starts exporter.py (Prometheus metrics, port 8000)
#   /entrypoint.sh server     → starts server.py   (MCP server, port 8001)
#
# Runs as root briefly to fix SSH key permissions, then drops to the
# non-root 'mcp' user. Docker volume mounts are 644 by default; SSH
# refuses private keys that are world-readable.

PROCESS="${1:-exporter}"

if [ -f /app/id_ed25519 ]; then
    cp /app/id_ed25519 /tmp/id_ed25519
    chmod 600 /tmp/id_ed25519
    chown mcp /tmp/id_ed25519
fi

case "$PROCESS" in
    exporter)
        exec su -s /bin/bash mcp -c "python /app/exporter.py"
        ;;
    server)
        exec su -s /bin/bash mcp -c "python /app/server.py"
        ;;
    *)
        echo "Unknown process '${PROCESS}'. Use 'exporter' or 'server'." >&2
        exit 1
        ;;
esac

