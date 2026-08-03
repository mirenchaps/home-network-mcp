# home-network-mcp/Dockerfile
#
# Builds a single image used by two separate K3s Deployments:
#   - exporter pod: runs exporter.py (Prometheus metrics, port 8000)
#   - server pod:   runs server.py  (MCP server, streamable-HTTP, port 8001)
#
# Which process starts is controlled by the CMD arg passed via entrypoint.sh:
#   CMD ["/entrypoint.sh", "exporter"]   ← default (exporter Deployment)
#   CMD ["/entrypoint.sh", "server"]     ← MCP server Deployment
#
# Build:  docker build -t home-network-mcp .
# Docs: https://docs.docker.com/reference/dockerfile/

# --- build stage: install dependencies into a clean layer ---
FROM python:3.12-slim AS builder

WORKDIR /app

# Copy only the requirements file first so Docker can cache this layer.
# If requirements.txt hasn't changed, this layer is reused on every build.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- runtime stage: copy installed packages + app code ---
FROM python:3.12-slim

WORKDIR /app

# Install openssh-client (SSH to Pi), ca-certificates + libssl3 (pywinrm TLS),
# and PowerShell 7 (pwsh, for scan_network in the MCP server pod).
# The exporter pod doesn't use pwsh, but both pods share this image —
# the extra ~100MB is the trade-off for a single image to maintain.
#
# PowerShell install method: Microsoft's official apt repo for Debian bookworm.
# Docs: https://learn.microsoft.com/en-us/powershell/scripting/install/install-debian
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-client \
        ca-certificates \
        libssl3 \
        curl \
        gnupg \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/microsoft-debian-bookworm-prod bookworm main" > /etc/apt/sources.list.d/microsoft.list \
    && apt-get update && apt-get install -y --no-install-recommends powershell \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source — both the exporter and the MCP server
COPY exporter.py runner.py winrm_collect.py homebridge.py server.py ./
COPY scripts/ ./scripts/

# Trust the WinRM host's self-signed cert.
# update-ca-certificates reads every .crt in /usr/local/share/ca-certificates/
# and adds it to the system trust store at /etc/ssl/certs/ca-certificates.crt.
# PSWSMan uses that trust store when validating the HTTPS WinRM connection.
COPY certs/winrm-host.pem /usr/local/share/ca-certificates/winrm-host.crt
RUN update-ca-certificates

# Create a non-root user to run the exporter.
# The entrypoint runs as root briefly to fix SSH key permissions, then drops to this user.
RUN useradd --system --no-create-home --shell /bin/false mcp

# The exporter serves metrics on port 8000; the MCP server runs on port 8001.
EXPOSE 8000 8001

# Credentials are injected at runtime via environment variables — never baked in.
ENV GRAFANA_REMOTE_WRITE_URL=""
ENV GRAFANA_USER_ID=""
ENV GRAFANA_API_KEY=""
ENV WINRM_USERNAME=""
ENV WINRM_PASSWORD=""
ENV HOMEBRIDGE_HOST=""
ENV HOMEBRIDGE_USERNAME=""
ENV HOMEBRIDGE_PASSWORD=""

# Fix SSH key permissions at startup — Docker mounts files as 644 but SSH
# requires private keys to be 600 or stricter, otherwise it refuses to use them.
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Default runs the exporter. The MCP server Deployment overrides this with
# CMD ["/entrypoint.sh", "server"] in k8s/mcp-server-deployment.yaml.
CMD ["/entrypoint.sh", "exporter"]
