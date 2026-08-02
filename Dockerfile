# home-network-mcp/Dockerfile
#
# Builds the Prometheus metrics exporter into a Docker image.
# Only exporter.py and its dependencies are needed at runtime —
# server.py (the MCP server) is a separate process run outside Docker.
#
# Build:  docker build -t home-network-mcp .
# Run:    docker run -p 8000:8000 \
#           -e GRAFANA_REMOTE_WRITE_URL=... \
#           -e GRAFANA_USER_ID=... \
#           -e GRAFANA_API_KEY=... \
#           home-network-mcp
#
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

# Install PowerShell 7 (for WinRM calls) and openssh-client (for SSH to Pi).
# dpkg -i exits with code 1 on missing deps — || true lets the chain continue
# so apt-get install -f can resolve those deps immediately after.
# PowerShell release: https://github.com/PowerShell/PowerShell/releases
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-client \
        ca-certificates \
        libssl3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY exporter.py runner.py winrm_collect.py ./
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

# The exporter serves metrics on port 8000
EXPOSE 8000

# Credentials are injected at runtime via environment variables — never baked in.
# See alloy-config.river for the variable names Grafana Alloy expects.
ENV GRAFANA_REMOTE_WRITE_URL=""
ENV GRAFANA_USER_ID=""
ENV GRAFANA_API_KEY=""
ENV WINRM_USERNAME=""
ENV WINRM_PASSWORD=""

# Fix SSH key permissions at startup — Docker mounts files as 644 but SSH
# requires private keys to be 600 or stricter, otherwise it refuses to use them.
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
